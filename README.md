# 教材二手比价购买决策助手

一个 Claude Code Skill，帮助大学生在孔夫子旧书网、多抓鱼、拼多多、闲鱼四大平台搜索二手教材，用 Beam Search 算法计算全局最优购买方案，一键生成三档推荐报告。

## 效果预览

输入教材清单 → 自动跨平台比价 → 输出购买报告：

```
📚 新学期教材购买报告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 教材清单：5 本 ｜ 📅 数据采集时间：2026-09-01 14:30

🏆 推荐方案：⭐ 性价比推荐
总价：¥87.3（预估）｜ 比全买新书省 ¥142.7 ｜ 够吃 10 顿拼好饭

│ # │ 书名      │ 平台  │ 价格 │ 品相    │ 链接   │
├───┼──────────┼──────┼──────┼────────┼────────┤
│ 1 │ 数据结构  │ 孔夫子 │ ¥12  │ B(八五品)│ 🔗 直达 │
│ 2 │ 组成原理  │ 闲鱼   │ ¥18  │ B(八成)  │ 🔗 直达 │
│ 3 │ 操作系统  │ 拼多多 │ ¥22  │ A(全新)  │ 🔗 直达 │
│ 4 │ 高等数学  │ 多抓鱼 │ ¥15  │ A(良好)  │ 🔗 直达 │
│ 5 │ 大学英语  │ 孔夫子 │ ¥8   │ C(七品)  │ 🔗 直达 │

📊 三档方案对比
│ 💰 极限省钱 │ ¥58.5 │ C+  │
│ ⭐ 性价比   │ ¥87.3 │ B+  │
│ 🎯 品质优先 │ ¥125  │ A   │
```

## 安装

### 方法一：复制到 Skills 目录

```bash
# 将整个 textbook-bargain-hunter 文件夹复制到 Claude Code 的 skills 目录
cp -r textbook-bargain-hunter ~/.claude/skills/
```

### 方法二：在 settings.json 中引用

在 `.claude/settings.json` 中添加：

```json
{
  "skills": {
    "textbook-bargain-hunter": {
      "path": "/path/to/textbook-bargain-hunter"
    }
  }
}
```

## 使用方法

在 Claude Code 中说以下任意一句即可触发：

- 「帮我买教材」
- 「二手教材比价」
- 「新学期教材清单」
- 「搜一下这几本课本的二手价格」

然后按照引导提供教材清单，尽量包含以下信息：

| 字段 | 重要程度 | 示例 |
|------|---------|------|
| 书名 | 🔴 必须 | 数据结构（C语言版） |
| 作者 | 🟡 强烈建议 | 严蔚敏 |
| ISBN | 🟡 强烈建议 | 9787302147510 |
| 版本号 | 🟡 强烈建议 | 第二版 |
| 出版社 | 🟢 锦上添花 | 清华大学出版社 |

> 💡 ISBN 在教材封底的条形码上方。

## 依赖

- Claude Code（提供 `WebSearch` 和 `WebFetch` 工具）
- Python 3.7+（仅标准库，无第三方依赖）

## 文件结构

```
textbook-bargain-hunter/
├── SKILL.md                    # Claude Code 操作手册
├── README.md                   # 本文件
└── scripts/
    ├── optimizer.py            # Beam Search 推荐方案计算器
    ├── formatter.py            # Markdown 报告生成器
    └── sample_search_results.json  # 示例数据（可用于测试）
```

## 快速测试

用自带的示例数据测试 optimizer + formatter 是否正常工作：

```bash
# 生成推荐方案
python scripts/optimizer.py scripts/sample_search_results.json -o optimized_plan.json

# 生成购买报告
python scripts/formatter.py optimized_plan.json --search-data scripts/sample_search_results.json -o report.md
```

## 核心特性

- **四平台比价**：孔夫子旧书网、多抓鱼、拼多多、闲鱼
- **标价陷阱防御**：强制进入详情页取真实价格
- **Beam Search 算法**：取代穷举，支持 8+ 本教材的大规模比价
- **三档策略**：极限省钱 / 性价比推荐 / 品质优先
- **品相统一评级**：A/B/C/D 四级内部标准
- **版本精确匹配**：自动从标题提取版本号校验
- **阶梯运费模型**：同店多本运费递增估算
- **零外部依赖**：Python 标准库即装即用

## 注意事项

- 价格来自搜索时刻，可能实时变动
- 运费为估算值，实际以平台结算页为准
- 闲鱼 PC 端搜索可能不完整
- 系统仅提供信息聚合，不代下单/代付款
- 商品链接可能随时间失效

## 许可

MIT
