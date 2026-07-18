# 输出模板（v2 · 六件套）

> 本文件说明 `zach-search-term-report-analyzer` v2 的输出文件结构与完成信号模板。
> 字段级权威 schema（payload / run_summary / HTML 契约）见 `architecture.md` §5–6；冲突时以 architecture.md 为准。

---

## 1. 六件套总览

统一保存到 `outputs/search-term-report-analyzer/{brand}/`，文件名前缀 `{YYYY-MM-DD}_{品牌}_{ASIN}`：

| # | 文件 | 格式 | 用途 | 主要受众 |
|---|------|------|------|----------|
| 1 | `..._搜索词报告分析.md` | .md | 主报告：结论 + 各决策分节表 | 运营 / 归档 |
| 2 | `..._搜索词分析明细.csv` | .csv | 全词明细，可进 Excel 二次加工 | 运营 |
| 3 | `..._否词清单.csv` | .csv | 可直接对照后台执行的否词候选 | 运营（执行前须确认） |
| 4 | `..._搜索词分析操作台.html` | .html | 交互工作台：筛选/排序/勾选/导出 | 运营做决策落地 |
| 5 | `..._搜索词分析汇报.html` | .html | 静态结论页：KPI 卡 + 分布图 | 团队汇报 / 上级 |
| 6 | `..._run_summary.json` | .json | 验收指标 + 文件清单 | Step 4 验收自检 |

中间产物（`workbook.json` / `roots_for_review.md` / `root_classifications.json`）留在 `intermediate/{YYYY-MM-DD}_{ASIN}/` 子目录备查，不算交付物。

## 2. 主报告 .md 结构

开头必须带可追溯的 YAML 元数据头：

```yaml
---
created: YYYY-MM-DD HH:MM
topic: {品牌} {ASIN} 搜索词报告分析
type: 广告搜索词报告分析
data_sources:
  - 搜索词报告: 用户输入文件名或来源说明
  - Listing上下文: 来源说明或无
status: DONE / DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT
---
```

正文分节（按输出优先级排序，见 `decision_rules.md` §5）：

1. **分析对象与口径**：品牌 / ASIN / 报告类型 / 数据时间范围 / 基准 CVR·ACOS / 目标 ACOS / 实际生效阈值
2. **核心结论摘要**：否词 N、放量 N、降 bid N、Listing 反馈 N、待判定占比（词数/花费口径各一）、低量池规模、浪费花费
3. **否词候选**（含 root 级 negative phrase 建议单独段）
4. **放量候选**
5. **降 bid / 控成本**
6. **属性词 / 场景词洞察（listing_feedback）**：广告侧建议与 Listing 侧建议拆开写
7. **品牌词 / 竞品词 bucket**（单列，不与泛词混排）
8. **人工复核项（manual_review）**：逐项写清为什么需要人
9. **低量长尾池（pool）**：只给汇总统计（词数/点击/花费/订单）+ "汇总监控，不逐词决策"声明
10. **7/14/30 天趋势要点**
11. **方法论脚注**：词根继承机制一句话说明 + 数据来源与时间范围

全文区分「📊 数据事实」与「💡 分析推断」；无 sales 时不硬给 ACOS；未使用字段显式声明。

## 3. 明细 .csv 字段

每词一行，列与 payload.terms 对齐（权威见 architecture.md §6）：

`search_term, category, relevance, decision, confidence, basis(term|root|pool), reason, root, match_types, clicks, spend, orders, sales, cvr, acos, cpc, ctr, w7_clicks, w7_cvr, w7_acos, w14_clicks, w14_cvr, w14_acos, w30_clicks, w30_cvr, w30_acos, trend, listing_flag, negative_match_suggestion`

utf-8-sig 编码（Excel 直开不乱码）。

## 4. 否词清单 .csv

- 主体：`search_term, match_type(negative exact), reason, spend, clicks` —— 每行一个词级否词候选。
- **root 级 negative phrase 建议单独段**（整词根无关且成员 ≥3 时）：`root, match_type(negative phrase), reason, term_count, spend`。
- 清单是**候选**不是指令：risk-level = medium，执行前必须用户确认。

## 5. 操作台 HTML（给运营做决策落地）

- 顶部摘要卡：总花费 / 浪费花费 / 否词数 / 放量数 / 待判定占比 / 低量池规模 / 基准 CVR·ACOS
- 主表格：全量词；决策 tab 筛选（全部/否词/放量/降bid/Listing反馈/品牌/竞品/待判定/低量池）、类别下拉、文本搜索、任意列排序、行勾选
- 导出：否词清单 CSV / 放量清单 CSV / 勾选行 CSV（浏览器内直接下载）
- 词根视图 tab；低量池默认折叠（标注"汇总监控，不逐词决策"）
- 中文 UI、单文件自包含、零外部资源；打开若显示「payload 未注入」即视为生成失败，回 Step 3 排查

## 6. 汇报页 HTML（给团队/上级看结论）

- 结论优先：KPI 卡 → 决策分布横条图 → 花费去向（类别×决策）→ TOP10 否词表 → TOP10 放量表 → 属性/场景洞察 → 趋势要点 → 方法论脚注
- 「📊 数据事实」与「💡 分析推断」视觉区分；print 友好；零外部资源

## 7. run_summary.json（验收自检输入）

必含：`pending_ratio_terms` / `pending_ratio_spend`（目标 ≤0.10，超标不失败但显式告警）、pool 统计（词数/点击/花费/订单）、决策与类别的计数/花费分布、输出文件清单。Step 4 验收自检以此文件为准，不看脚本自我宣称。

## 8. 完成信号模板（3 句话，必含待判定占比）

```
1. 已完成 {品牌} / {ASIN} / {报告类型} 的搜索词报告分析（{起}~{止}，{N} 个唯一搜索词聚为 {R} 个词根）。
2. 否词候选 {N} 个（含词根级 phrase 建议 {M} 组）、放量候选 {K} 个、Listing 反馈 {L} 个；待判定占比 {X}%（词数口径）/ {Y}%（花费口径），目标 ≤10%{，超标原因：...}；低量池 {P} 词汇总监控。
3. 六件套已保存到 {目录}，操作台：{操作台.html 路径}，汇报页：{汇报.html 路径}。
```

待判定占比任一口径超 10% 时，第 2 句的"超标原因"不可省略（如：ASIN 串号词集中 / 报表样本过薄 / needs_listing_check 偏多）。
