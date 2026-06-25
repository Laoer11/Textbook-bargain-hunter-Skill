#!/usr/bin/env python3
"""
教材二手比价 — 推荐方案计算器
=================================
使用 Beam Search 算法，综合考虑品相硬约束、阶梯运费、平台满减优惠，
为 N 本教材计算三档（极限省钱 / 性价比 / 品质优先）购买方案。

用法:
    python optimizer.py search_results.json --strategy balanced
    python optimizer.py search_results.json                 # 默认输出三档方案
    python optimizer.py search_results.json --output plan.json

依赖: Python 3.7+ 标准库（无第三方依赖）
"""

import json
import argparse
import itertools
import re
from datetime import datetime, timezone, timedelta


# ============================================================================
# 数据加载
# ============================================================================

def load_data(path):
    """读取 Phase 1 搜索结果的 JSON 文件"""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # 支持单本和列表两种格式
    if isinstance(data, dict):
        return [data]
    return data


# ============================================================================
# 候选商品去重 (v2.1)
# ============================================================================

def normalize_shop_name(name):
    """归一化店铺名：去掉标点空格，统一'书店/书社/书屋'→'书'"""
    if not name:
        return ''
    name = re.sub(r'[（()）\[\]【】\s]', '', name)
    name = name.replace('书店', '书').replace('书社', '书').replace('书屋', '书')
    return name


def deduplicate_candidates(candidates):
    """
    对同一本书的候选商品去重。
    去重键 = ISBN + 版本匹配状态 + 内部品相 + 归一化店名
    保留价格（含运费）最低的一个。
    返回去重后的列表和去重统计信息。
    """
    seen = {}
    deduped = []
    removed_count = 0

    for cand in sorted(candidates, key=lambda c: c.get('price', 0) + c.get('shipping', 0)):
        key = (
            cand.get('isbn', ''),
            cand.get('edition_match', 'fuzzy'),
            cand.get('internal_condition', 'B'),
            normalize_shop_name(cand.get('shop', ''))
        )

        if key not in seen:
            seen[key] = cand
            deduped.append(cand)
        else:
            removed_count += 1
            # 如果当前候选项更便宜，替换
            existing = seen[key]
            if (cand.get('price', 0) + cand.get('shipping', 0) <
                    existing.get('price', 0) + existing.get('shipping', 0)):
                deduped.remove(existing)
                deduped.append(cand)
                seen[key] = cand

    return deduped, removed_count


# ============================================================================
# 品相硬约束过滤 (v2.0)
# ============================================================================

CONDITION_THRESHOLD = {
    'cheapest': ['A', 'B', 'C'],   # C 级及以上
    'balanced': ['A', 'B'],        # B 级及以上
    'quality': ['A'],              # 仅 A 级
}


def apply_condition_filter(candidates, strategy):
    """按策略过滤品相等级"""
    allowed = CONDITION_THRESHOLD.get(strategy, ['A', 'B'])
    filtered = [c for c in candidates if c.get('internal_condition', 'B') in allowed]
    return filtered


# ============================================================================
# Top-K 预剪枝
# ============================================================================

def pre_prune(candidates, strategy, beam_width):
    """
    对单本书的候选项按策略预排名，保留 top beam_width 个。
    减少 Beam Search 的分支因子。
    """
    candidates = apply_condition_filter(candidates, strategy)

    if strategy == 'quality':
        # 品质优先：按品相高→价格低排序
        condition_order = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
        sorted_cands = sorted(candidates,
                              key=lambda c: (condition_order.get(c.get('internal_condition', 'B'), 1),
                                             c.get('price', 0) + c.get('shipping', 0)))
    else:
        # 极限省钱和性价比：按预估到手价排序
        sorted_cands = sorted(candidates, key=lambda c: c.get('price', 0) + c.get('shipping', 0))

    return sorted_cands[:beam_width]


# ============================================================================
# 运费计算 (v2.0 阶梯模型)
# ============================================================================

# 平台运费规则特征（实际部署时可根据更多数据调整）
PLATFORM_SHIPPING_RULES = {
    '孔夫子': {'base_multiplier': 0.5},   # 首重后每本加收首重50%
    '多抓鱼': {'base_multiplier': 0.5},
    '拼多多': {'base_multiplier': 0.3},    # 拼多多包邮多，续重费更低
    '闲鱼': {'base_multiplier': 0.3},      # 个人卖家多包邮或面交
}


def calc_merged_shipping(items_same_shop):
    """
    阶梯运费模型: base + (n-1) * base * multiplier
    替代简单的 max()。
    """
    n = len(items_same_shop)
    if n <= 1:
        return sum(item.get('shipping', 0) for item in items_same_shop)

    individual_shippings = [item.get('shipping', 0) for item in items_same_shop]
    base = max(individual_shippings)  # 首本运费（取最高运费为基数）

    if base == 0:
        return 0  # 全部包邮

    platform = items_same_shop[0].get('platform', '')
    rule = PLATFORM_SHIPPING_RULES.get(platform, {'base_multiplier': 0.5})
    extra = (n - 1) * base * rule['base_multiplier']

    return round(base + extra, 2)


def calc_total_shipping(items):
    """计算全部商品的总运费（按店铺分组后合并计算）"""
    # 按 (平台, 店铺) 分组
    groups = {}
    for item in items:
        key = (item.get('platform', ''), item.get('shop', ''))
        groups.setdefault(key, []).append(item)

    total = sum(calc_merged_shipping(group) for group in groups.values())
    return round(total, 2)


# ============================================================================
# 平台优惠计算
# ============================================================================

def calc_platform_discounts(items):
    """
    计算平台满减优惠。
    当前支持：拼多多满60减8、满100减15
    """
    discounts = 0.0

    # 按平台分组
    platform_items = {}
    for item in items:
        plat = item.get('platform', '')
        platform_items.setdefault(plat, []).append(item)

    for plat, plat_items in platform_items.items():
        subtotal = sum(item.get('price', 0) for item in plat_items)

        if plat == '拼多多':
            if subtotal >= 100:
                discounts += 15
            elif subtotal >= 60:
                discounts += 8

        # 其他平台的满减规则可在此扩展

    return discounts


# ============================================================================
# 方案评分
# ============================================================================

def evaluate_full_plan(selections, strategy):
    """
    评估完整购买方案。
    策略差异通过「品相硬约束」+「评分调整」体现。
    """
    items = selections['items']
    n = len(items)

    # 基础价格
    base_total = sum(item.get('price', 0) for item in items)

    # 运费（同店合并）
    shipping = calc_total_shipping(items)

    # 平台优惠
    discounts = calc_platform_discounts(items)

    # 到手价
    total_price = round(base_total + shipping - discounts, 2)

    # 评分
    if strategy == 'cheapest':
        score = total_price

    elif strategy == 'balanced':
        # 性价比：价格为主，同店合并有便利加分
        shop_count = len(set((item.get('platform', ''), item.get('shop', '')) for item in items))
        convenience_bonus = (n - shop_count) * 2  # 每合并一单减 ¥2
        score = round(total_price - convenience_bonus, 2)

    elif strategy == 'quality':
        # 品质优先：对不可靠平台加惩罚分
        reliability_penalty = sum(3 if item.get('platform') == '闲鱼' else 0 for item in items)
        score = round(total_price + reliability_penalty, 2)

    else:
        score = total_price

    return {
        'items': items,
        'base_total': round(base_total, 2),
        'shipping': shipping,
        'discounts': round(discounts, 2),
        'total_price': total_price,
        'score': score,
        'shop_count': len(set((item.get('platform', ''), item.get('shop', '')) for item in items)),
        'platforms_used': list(set(item.get('platform', '') for item in items)),
    }


def evaluate_partial(beam, strategy):
    """评估部分方案（Beam Search 中间步骤用）"""
    n = len(beam['selections'])
    if n == 0:
        return 0
    price = sum(item.get('price', 0) for item in beam['selections'])
    return price  # 中间步骤只看价格，运费和优惠最后统一算


# ============================================================================
# Beam Search (v2.0)
# ============================================================================

def adaptive_beam_width(num_books):
    """自适应 Beam Width"""
    if num_books <= 3:
        return 10
    elif num_books <= 6:
        return 5
    else:
        return 3


def beam_search(books, all_candidates_by_isbn, strategy, beam_width=None):
    """
    Beam Search 主算法。
    每一步为一本书选商品，保留 beam_width 个最优部分方案。
    复杂度 O(N * M * beam_width)，而非 O(M^N)。
    """
    num_books = len(books)
    if beam_width is None:
        beam_width = adaptive_beam_width(num_books)

    # 初始 beam：空方案
    beams = [{'selections': [], 'total_price': 0}]

    for i, book in enumerate(books):
        isbn = book.get('isbn', '')
        title = book.get('book', book.get('title', f'Book-{i}'))

        # 获取这本书的候选商品
        raw_candidates = all_candidates_by_isbn.get(isbn, [])
        if not raw_candidates:
            raw_candidates = all_candidates_by_isbn.get(title, [])

        # 去重 + 品相过滤 + 预剪枝
        deduped, _ = deduplicate_candidates(raw_candidates)
        candidates = pre_prune(deduped, strategy, beam_width)

        if not candidates:
            # 无候选，跳过这本书
            continue

        new_beams = []
        for beam in beams:
            for cand in candidates:
                new_selections = beam['selections'] + [dict(cand, book_title=title, book_isbn=isbn)]
                new_beam = {
                    'selections': new_selections,
                    'base_price': beam.get('base_price', 0) + cand.get('price', 0),
                }
                new_beams.append(new_beam)

        # 保留 top beam_width 个
        new_beams.sort(key=lambda b: evaluate_partial(b, strategy))
        beams = new_beams[:beam_width]

    # 对最终 beam 中所有完整方案做完整评估
    final_plans = []
    for beam in beams:
        if len(beam['selections']) >= num_books:
            result = evaluate_full_plan({'items': beam['selections']}, strategy)
            final_plans.append(result)

    if not final_plans:
        return None

    # 按评分排序，返回最优方案
    final_plans.sort(key=lambda p: p['score'])
    return final_plans[0]


# ============================================================================
# 主入口
# ============================================================================

def run_optimizer(books_data, output_strategy=None):
    """
    对输入数据运行全部三档策略（或指定策略），返回完整结果。
    """
    books = []
    all_candidates = {}

    for book_data in books_data:
        book_key = book_data.get('isbn', book_data.get('book', book_data.get('title', '')))
        books.append({
            'book': book_data.get('book', book_data.get('title', '')),
            'isbn': book_data.get('isbn', ''),
        })
        all_candidates[book_data.get('isbn', book_data.get('book', ''))] = book_data.get('candidates', [])

    # 汇总统计
    total_raw = sum(len(book_data.get('candidates', [])) for book_data in books_data)
    total_after_dedup = 0
    for book_data in books_data:
        deduped, _ = deduplicate_candidates(book_data.get('candidates', []))
        total_after_dedup += len(deduped)

    strategies = ['cheapest', 'balanced', 'quality']
    if output_strategy:
        strategies = [output_strategy]

    plans = {}
    unavailable = {}
    for strategy in strategies:
        result = beam_search(books, all_candidates, strategy)
        if result:
            plans[strategy] = result
        else:
            # 诊断失败原因
            reasons = []
            for book in books:
                isbn = book.get('isbn', book.get('book', ''))
                candidates = all_candidates.get(isbn, [])
                filtered = apply_condition_filter(candidates, strategy)
                if len(candidates) > 0 and len(filtered) == 0:
                    reasons.append(f'{book["book"]}: 无满足品相要求的候选 (共{len(candidates)}个候选)')
                elif len(filtered) == 0:
                    reasons.append(f'{book["book"]}: 无候选商品')
            unavailable[strategy] = reasons if reasons else ['无可用方案']

    # 构建输出
    timestamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%dT%H:%M:%S+08:00')

    output = {
        'generated_at': timestamp,
        'meta': {
            'books_count': len(books),
            'candidates_raw': total_raw,
            'candidates_after_dedup': total_after_dedup,
            'strategies_computed': list(plans.keys()),
            'strategies_unavailable': unavailable,
            'algorithm': 'Beam Search',
            'beam_width': adaptive_beam_width(len(books)),
        },
        'plans': plans,
    }

    return output


def main():
    parser = argparse.ArgumentParser(
        description='教材二手比价 — 推荐方案计算器 (Beam Search)'
    )
    parser.add_argument(
        'input', help='search_results.json 文件路径'
    )
    parser.add_argument(
        '--strategy', '-s',
        choices=['cheapest', 'balanced', 'quality'],
        default=None,
        help='策略选择（不指定则输出三档方案）'
    )
    parser.add_argument(
        '--output', '-o',
        default=None,
        help='输出文件路径（默认打印到 stdout）'
    )
    parser.add_argument(
        '--beam-width', '-b',
        type=int,
        default=None,
        help='Beam Search 宽度（不指定则自适应）'
    )

    args = parser.parse_args()

    # 加载数据
    books_data = load_data(args.input)

    # 运行优化
    # 注意：--beam-width 在此处透传（当前实现使用自适应，可扩展为支持手动指定）
    result = run_optimizer(books_data, args.strategy)

    # 输出
    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_json)
        print(f'[OK] Optimized plan saved to: {args.output}')
    else:
        print(output_json)


if __name__ == '__main__':
    main()
