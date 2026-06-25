#!/usr/bin/env python3
"""
教材二手比价 — Markdown 推荐报告生成器
=========================================
读取 optimizer.py 输出的优化方案 JSON，生成用户可读的 Markdown 购买报告。

用法:
    python formatter.py optimized_plan.json
    python formatter.py optimized_plan.json --output report.md

依赖: Python 3.7+ 标准库（无第三方依赖）
"""

import json
import argparse
from datetime import datetime


# ============================================================================
# 数据加载
# ============================================================================

def load_plan(path):
    """读取 optimizer 输出的 JSON"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ============================================================================
# 策略名称映射
# ============================================================================

STRATEGY_LABELS = {
    'cheapest': '💰 极限省钱',
    'balanced': '⭐ 性价比推荐',
    'quality': '🎯 品质优先',
}

STRATEGY_DESC = {
    'cheapest': '最低价格，品相 C 级及以上即可',
    'balanced': '价格与品相平衡，B 级及以上，适合大多数人',
    'quality': '优先品相，仅 A 级，近全新/平台翻新',
}

PLATFORM_STATUS = {
    '孔夫子': '✅',
    '多抓鱼': '✅',
    '拼多多': '⚠️',
    '闲鱼': '💬',
}


# ============================================================================
# 报告片段生成
# ============================================================================

def format_price_table(items):
    """生成购买清单明细表"""
    rows = []
    for i, item in enumerate(items, 1):
        platform = item.get('platform', '?')
        status = PLATFORM_STATUS.get(platform, '')
        title = item.get('book_title', item.get('title', '?'))
        price = item.get('price', 0)
        shipping = item.get('shipping', 0)
        condition = item.get('internal_condition', '?')
        condition_orig = item.get('condition_original', '')
        condition_str = f'{condition}({condition_orig})' if condition_orig else condition
        edition = item.get('edition_match', 'fuzzy')
        edition_icon = '✅' if edition == 'exact' else '⚠️'
        url = item.get('url', '#')

        rows.append(
            f'│ {i} │ {title[:12]} │ {platform} {status}│ ¥{price:.0f} │ ¥{shipping:.0f} │ {condition_str} │ {edition_icon} │ [🔗 直达]({url}) │'
        )

    header = '│ # │ 书名 │ 平台 │ 价格 │ 运费 │ 品相 │ 版本 │ 链接 │'
    sep = '├───┼──────────┼────────┼──────┼──────┼──────┼──────┼──────────┤'

    return '\n'.join([header, sep] + rows)


def format_comparison_table(plans, unavailable=None):
    """生成三档方案对比表"""
    rows = []
    for strategy in ['cheapest', 'balanced', 'quality']:
        plan = plans.get(strategy)
        if not plan:
            # 策略不可用
            label = STRATEGY_LABELS.get(strategy, strategy)
            reason = ''
            if unavailable and strategy in unavailable:
                reasons = unavailable[strategy]
                reason = reasons[0] if reasons else '条件不满足'
            rows.append(f'│ {label} │ — │ — │ — │ {reason} │')
            continue

        label = STRATEGY_LABELS.get(strategy, strategy)
        total = plan.get('total_price', 0)

        # 统计品相分布
        conditions = [item.get('internal_condition', '?') for item in plan.get('items', [])]
        if all(c == 'A' for c in conditions):
            cond_label = '全 A'
        elif all(c in ('A', 'B') for c in conditions):
            cond_label = 'B+'
        elif all(c in ('A', 'B', 'C') for c in conditions):
            cond_label = 'C+'
        else:
            cond_label = '/'.join(sorted(set(conditions)))

        shops = plan.get('shop_count', len(plan.get('items', [])))
        # 到货时间估计
        platforms = set(item.get('platform', '') for item in plan.get('items', []))
        if '闲鱼' in platforms:
            delivery = '3-10天'
        elif '拼多多' in platforms:
            delivery = '3-7天'
        else:
            delivery = '2-5天'

        rows.append(f'│ {label} │ ¥{total:.1f} │ {cond_label} │ {shops} 个店铺 │ {delivery} │')

    header = '│ 方案 │ 总价 │ 品相 │ 店铺数 │ 到货 │'
    sep = '├──────────┼────────┼──────┼─────────┼────────┤'

    return '\n'.join([header, sep] + rows)


def generate_notes(plan, strategy, data):
    """生成注意事项"""
    notes = []
    items = plan.get('items', []) if plan else []

    # 运费估算标注
    notes.append('- ⚠️ 运费为估算值，实际以平台结算页为准')

    # 闲鱼提示
    xianyu_items = [item for item in items if item.get('platform') == '闲鱼']
    if xianyu_items:
        notes.append('- 💬 闲鱼个人卖家，可能有议价空间，建议先联系卖家确认库存')

    # 同店合并提示
    shop_items = {}
    for item in items:
        key = (item.get('platform', ''), item.get('shop', ''))
        shop_items.setdefault(key, []).append(item)
    multi_shops = {k: v for k, v in shop_items.items() if len(v) >= 2}
    for (plat, shop), shop_items_list in multi_shops.items():
        titles = [it.get('book_title', '?') for it in shop_items_list]
        notes.append(f'- 📦 {plat}「{shop}」的 {len(shop_items_list)} 本可合并下单省运费（{"、".join(titles)}）')

    # 拼多多满减提醒
    pdd_items = [item for item in items if item.get('platform') == '拼多多']
    if pdd_items:
        pdd_subtotal = sum(item.get('price', 0) for item in pdd_items)
        if pdd_subtotal < 60:
            notes.append(f'- 🏷️ 拼多多当前小计 ¥{pdd_subtotal:.0f}，差 ¥{60 - pdd_subtotal:.0f} 可凑满 60 减 8')
        notes.append('- 🏷️ 拼多多满减券需手动领取（商品页有领取入口）')

    # 时间戳
    ts = data.get('generated_at', datetime.now().strftime('%Y-%m-%d %H:%M'))
    notes.append(f'- 📅 数据采集时间：{ts}，价格可能已变化')
    notes.append('- 🔗 链接有效性无法保证，请以平台实际页面为准')
    notes.append('- 🛡️ 系统仅提供信息聚合，不对商品质量做担保')

    return '\n'.join(notes)


def format_degraded_platforms(books_data):
    """格式化平台状态行"""
    all_degraded = set()
    all_success = set()
    for book_data in books_data:
        degraded = book_data.get('degraded_platforms', [])
        for d in degraded:
            if isinstance(d, dict):
                all_degraded.add(d.get('platform', ''))
            else:
                all_degraded.add(d)
        for cand in book_data.get('candidates', []):
            all_success.add(cand.get('platform', ''))

    parts = []
    for plat in ['孔夫子', '多抓鱼', '拼多多', '闲鱼']:
        if plat in all_degraded:
            parts.append(f'{plat} ❌')
        elif plat in all_success:
            parts.append(f'{plat} ✅')
        else:
            parts.append(f'{plat} —')

    return ' ｜ '.join(parts)


# ============================================================================
# 主报告生成
# ============================================================================

def generate_report(plan_data, books_data=None):
    """
    生成完整 Markdown 报告。
    plan_data: optimizer 输出的 JSON
    books_data: 原始搜索数据（可选，用于平台状态等信息）
    """
    plans = plan_data.get('plans', {})
    meta = plan_data.get('meta', {})
    ts = plan_data.get('generated_at', datetime.now().strftime('%Y-%m-%d %H:%M'))

    # 默认推荐的策略
    default_strategy = 'balanced'
    if default_strategy not in plans:
        default_strategy = next(iter(plans.keys()), 'balanced')

    recommended = plans.get(default_strategy)

    lines = []

    # 标题
    lines.append('📚 新学期教材购买报告')
    lines.append('━' * 60)

    # 基本信息
    lines.append(f'📋 教材清单：{meta.get("books_count", "?")} 本')
    lines.append(f'📅 数据采集时间：{ts}')
    lines.append('⚠️  价格实时变动，请以平台实际页面为准')

    if books_data:
        lines.append(f'📊 数据来源：{format_degraded_platforms(books_data)}')

    lines.append('━' * 60)
    lines.append('')

    # 推荐方案
    strategy_label = STRATEGY_LABELS.get(default_strategy, default_strategy)
    new_book_price = 230  # 默认新书价（可在 search_results 中指定）
    saving = new_book_price - (recommended.get('total_price', 0) if recommended else 0)
    meals = max(0, int(saving / 13))  # 按拼好饭 ~¥13/顿 估算

    lines.append(f'🏆 推荐方案：{strategy_label}')
    lines.append(f'总价：¥{recommended["total_price"]:.1f}（预估）｜ 比全买新书省 ¥{saving:.1f} ｜ 够吃 {meals} 顿拼好饭' if recommended else '无可用方案')
    lines.append('')

    if recommended:
        lines.append(format_price_table(recommended.get('items', [])))
        lines.append('')

    # 三档方案对比
    lines.append('📊 三档方案对比')
    lines.append(format_comparison_table(plans, meta.get('strategies_unavailable', {})))
    lines.append('')

    # 注意事项
    lines.append('⚠️ 注意事项')
    lines.append(generate_notes(recommended, default_strategy, plan_data))
    lines.append('')

    # 底部
    lines.append('━' * 60)
    lines.append('💡 提示：点击 🔗 直达链接跳转到对应平台购买。如商品已下架或涨价，请告知我重搜。')

    return '\n'.join(lines)


# ============================================================================
# 主入口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='教材二手比价 — Markdown 推荐报告生成器'
    )
    parser.add_argument(
        'input', help='optimizer 输出的 JSON 文件路径（如 optimized_plan.json）'
    )
    parser.add_argument(
        '--output', '-o',
        default=None,
        help='输出 Markdown 文件路径（默认打印到 stdout）'
    )
    parser.add_argument(
        '--search-data', '-s',
        default=None,
        help='原始 search_results.json（可选，用于更丰富的平台状态信息）'
    )

    args = parser.parse_args()

    plan_data = load_plan(args.input)

    books_data = None
    if args.search_data:
        try:
            with open(args.search_data, 'r', encoding='utf-8') as f:
                books_data = json.load(f)
            if isinstance(books_data, dict):
                books_data = [books_data]
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    report = generate_report(plan_data, books_data)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f'[OK] Report saved to: {args.output}')
    else:
        print(report)


if __name__ == '__main__':
    main()
