---
name: zach-product-research
description: 基于 Sorftime MCP 的亚马逊选品分析 Skill，用于发现潜力市场、验证竞争格局、完成属性标注与交叉分析，并输出 Go/No-Go 结论及标准化市场调研交付物。
argument-hint: "[产品/类目关键词] [站点]"
user-invocable: true
---

# 选品分析器

## 定位

`zach-product-research` 用于亚马逊新品上架工作流的第一步：先判断市场值不值得进入，再决定后续是否投入竞品拆解、定价、Listing 文案和广告预算。

核心目标：

1. 发现有机会的细分类目或目标子赛道
2. 识别竞争格局、进入门槛和新品友好度
3. 对 Top100 产品做属性标注与交叉分析
4. 给出 `GO / CONDITIONAL GO / HOLD / NO-GO` 决策
5. 产出可复核的市场调研四件套

## 适用场景

- 用户只有一个产品标题或一个品类词，想先判断能不能做
- 用户准备上新，需要先完成市场调研和选品论证
- 用户已经有供应链资源，想找更合适的切入子市场
- 用户需要标准化交付，方便团队内部审核和复盘

## 前置条件

- Sorftime MCP 已配置并可调用
- Python 3.9+，安装 `openpyxl`（`pip install openpyxl`）
- 明确目标站点，默认 `US`

## 使用方法

### 方式1：指定产品和站点
```
/zach-product-research bluetooth speaker US
```

### 方式2：自然语言
```
帮我用 Sorftime 分析美国站蓝牙音箱选品机会
```

### 方式3：带约束条件
```
帮我找美国站月销1000+、价格$15-30、评论门槛低的潜力产品
```

## 执行步骤

当调用此 Skill 时，执行以下流程：

1. **读取完整方法论** - 加载 `skills/zach-product-research/SKILL.md`
2. **信息收集** - 交互式确认目标站点、选品场景、约束条件
3. **调用 Sorftime MCP** - 按方法论调用数据工具（⛔ 必调：`category_search_from_product_name`、`category_report`、`category_trend`、`keyword_detail`、`product_reviews`、`product_detail`）
4. **市场机会发现** - 类目扫描 + 关键词多维度对比 + 潜力产品预筛
5. **维度自发现** - 标题词频聚类 + 关键词延伸词 + product_detail 属性 Key 提取 → 候选维度列表 → 用户确认
6. **产品属性标注** - Top100 标题解析提取多维度属性 → 对"未知"项批量调 `product_detail` 验证
7. **多维度交叉分析** - 维度交叉矩阵 → 供需缺口自动识别 → 品牌集中度分析
8. **新品分析** - Top100 新品占比 + 时间分桶 + 新品友好度评级
9. **竞争格局验证** - 竞品选择逻辑表（6-10 个竞品）+ 差评维度归类
10. **进入壁垒评估** - 6 类壁垒评估 + 站点合规速查
11. **投入产出测算** - 毛利/净利/ACOS目标/净利率
12. **Go/No-Go 综合评分** - 5 维度加权评分 → 决策
13. **交付前自检 + 一键渲染** - 组装 unified_payload.json v2 → `render_deliverables.py all`

## 核心输出（四件套）

| 类型 | 文件命名 | 用途 |
|------|----------|------|
| 报告 | `[日期]_[站点]_[关键词]_市场调研报告_[version].md` | 完整分析报告（10 章结构） |
| 精简 | `[日期]_[站点]_[关键词]_精简报告_[version].html` | 快速浏览关键结论 |
| 看板 | `[日期]_[站点]_[关键词]_可视化看板_[version].html` | 交互式 Dashboard |
| 数据 | `[日期]_[站点]_[关键词]_市场调研_数据_[version].xlsx` | 多 Sheet 明细数据 |

## 下游对接

选品报告可作为后续 Listing 优化、定价策略、广告策略的输入。

## 数据诚信规则

- **绝不捏造数据**：所有数据必须来自 Sorftime MCP 调用结果
- **标注数据来源**：每个数据点标注来源工具
- **区分事实与推测**：事实用数据支撑，推测必须标注「⚠️ 推测」

## 完整方法论

详见 `skills/zach-product-research/SKILL.md`
