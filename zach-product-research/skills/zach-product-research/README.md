# 选品分析器（Product Research）

基于 **Sorftime MCP** 的选品分析 Skill，帮助发现高潜力市场机会、验证竞争格局、测算投入产出。

## 前置条件

- **Sorftime MCP 已配置并启用**（Cursor Settings → Tools & MCP → sorftime 为 On）

## 使用方法

```
/zach-product-research laptop backpack US
```

或自然语言：
```
帮我用Sorftime分析一下美国站蓝牙耳机选品机会
```

## 核心流程

1. **发现机会市场** - 类目扫描、关键词挖掘、潜力产品初筛
2. **验证竞争格局** - 类目深度、竞品详细、关键词竞争
3. **投入产出测算** - 财务公式、CPC、ACOS、净利率
4. **差异化建议** - 痛点改进、卖点提炼、定价策略

## 主要 Sorftime MCP 工具

- `search_categories_broadly` - 多维度广泛搜索类目
- `category_search_from_product_name` - 按产品名搜索类目
- `category_report` - 类目 Top100 报告
- `potential_product` - 潜力产品搜索
- `keyword_search_results` - 关键词搜索结果
- `keyword_detail` - 关键词详情
- `product_detail` - 产品详情
- `product_reviews` - 产品评论
- `ali1688_similar_product` - 1688 货源参考

## 输出（三件套 + 原始数据，便于人工验证）

- **报告**：`[日期]_[站点]_[关键词]_市场调研报告_[version].md`
- **精简**：`[日期]_[站点]_[关键词]_精简报告_[version].html`
- **数据**：`[日期]_[站点]_[关键词]_市场调研_数据_[version].xlsx`（多 Sheet）
  - 首 Sheet 为 **数据来源说明**（每 Sheet 注明来源工具、数据含义、关键参数、日期）
  - 总结：市场概况、品牌_竞品格局、进入壁垒评估、Go-NoGo评分卡
  - 明细：类目销量Top100_明细、关键词自然位产品_明细、潜力产品_明细、竞品选择逻辑、竞品差评摘要、关键词对比_分段、新品分析、1688参考（按实际调用）
- **原始/中间数据**：`top100_raw.json`、`cross_analysis.json`、`voc_analysis.json` 等
- **存储位置**：`工作成果/brands/[品牌名]/市场调研/[品类slug]/[version]/` 或 `工作成果/brands/_选品/市场调研/[品类slug]/[version]/`

## 生成与校验脚本

Skill 自带脚本：

`skills/zach-product-research/scripts/render_deliverables.py`

统一输入一个 JSON 数据包，自动生成三件套并校验。

```bash
python skills/zach-product-research/scripts/render_deliverables.py all --input payload.json
```

脚本会检查：
- 三件套是否齐全
- Markdown 是否有 YAML 头
- Excel 首 Sheet 是否为 `数据来源说明`
- Excel 是否包含 `品牌_竞品格局`、`进入壁垒评估`、`Go-NoGo评分卡`
- 文件名和目录结构是否符合 skill 规范

**Windows 用户注意**：在 Windows 上运行脚本如遇编码或路径问题，请参考 [`scripts/WINDOWS_USAGE.md`](./scripts/WINDOWS_USAGE.md) 获取详细指南。

详见 `SKILL.md`「报告与数据文件存储」及 CLAUDE.md「外部数据调用规范」。

## 下游对接

选品报告 → 可选先接 `zach-report-dashboard-renderer` 生成更完整的 Dashboard HTML，再进入新品上架工作流后续步骤；也可以直接作为启动模板输入继续执行。
