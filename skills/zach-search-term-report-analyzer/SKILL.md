---
name: zach-search-term-report-analyzer
description: |
  分析 Amazon Ads SP / SB / SD 搜索词报告。确定性脚本负责清洗、时间窗聚合、词根聚类和决策计算，AI 助手或人工负责词根级语义分类；通过词根继承减少长尾词的待判定比例，输出 Markdown、CSV、HTML 和 JSON 六类结果。
  使用时机：判断搜索词是否应该否定、控成本、继续测试或放量，分析 7/14/30 天 CVR 与 ACOS 变化，或者提炼可反馈给 Listing 的属性词和场景词。
  触发词：/zach-search-term-report-analyzer
triggers:
  - "/zach-search-term-report-analyzer"
benefits-from: []
user-invocable: true
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep]
risk-level: medium
---

# Amazon 搜索词报告分析（v2）

## 工作方式

v2 将确定性计算与语义判断分开：

```text
搜索词报告
  → Stage A：清洗、7/14/30 天聚合、词根聚类、硬标签
  → Stage B：AI 助手或人工完成词根语义分类
  → Stage C：严格校验、词根决策继承、六类结果渲染
```

词根继承用于处理低样本长尾词：当单个搜索词样本不足、但所属词根样本足够时，该词继承词根级判断；词与词根样本都不足时进入低量长尾池 `pool`，汇总监控但不伪装成待判定。

## 需要的输入

| 参数 | 必须 | 默认值 | 说明 |
|------|------|--------|------|
| 搜索词报告 | 是 | — | CSV / XLSX / XLSM / XLS |
| ASIN | 是 | — | 一次只分析一个 ASIN |
| 品牌 | 是 | — | 用于品牌词硬标签与输出命名 |
| 目标 ACOS | 是 | — | 使用小数，例如 `0.20` |
| 站点 | 否 | US | 用于可选的 Listing 上下文抓取 |
| 报告类型 | 否 | 自动识别 | SP / SB / SD |
| 时间窗 | 否 | 7,14,30 | 用逗号分隔 |
| Listing 上下文 | 否 | 空 | 可传入本地 Markdown / 文本快照 |

如果报告包含多个 ASIN，先从清洗元数据中列出候选，再让用户选定一个；不要混合分析。目标 ACOS、品牌或 ASIN 缺失时必须补齐，不能用隐藏默认值代替。

## 本地参考

- `references/architecture.md` — v2 管线、数据契约与决策顺序
- `references/field_mapping.md` — SP / SB / SD 字段映射
- `references/decision_rules.md` — 决策规则的运营解释
- `references/term_classification.md` — Stage B 分类枚举与 JSON schema
- `references/output_template.md` — 六类输出与完成信号
- `scripts/prepare_search_term_analysis.py` — Stage A
- `scripts/finalize_search_term_report.py` — Stage C
- `scripts/clean_search_term_report.py` — 清洗底层
- `scripts/fetch_listing_context.py` — 可选 Listing 上下文抓取

## Stage A：准备分析工作簿

```bash
python3 skills/zach-search-term-report-analyzer/scripts/prepare_search_term_analysis.py \
  <input_file> \
  --asin B0XXXXXXXX \
  --brand ExampleBrand \
  --site US \
  --target-acos 0.20 \
  --windows 7,14,30 \
  --listing-context-file <optional-listing-context.md> \
  --output-dir outputs/search-term-report-analyzer/ExampleBrand/intermediate/
```

`--listing-context-file` 与 `--report-type` 均为可选参数，不使用时删除对应命令行。

Stage A 只做可复现计算：

- 标准化字段、搜索词和数值格式
- 识别无法解析的非空数值，禁止静默清零
- 按 7/14/30 天窗口聚合并重新计算 CTR、CVR、ACOS、ROAS
- 聚类搜索词词根
- 标记确定性的 `asin_term` 与 `brand_term`

它会在中间目录生成：

- `workbook.json`：term、root、窗口指标和分类请求
- `roots_for_review.md`：按花费排序的待分类词根表

## Stage B：完成词根分类

读取 `roots_for_review.md`、`workbook.json` 中的 Listing 上下文和 `references/term_classification.md`，为 `classification_request.roots_to_classify` 中每一个词根填写：

- `category`
- `relevance`
- 一句话 `note`
- 可选的 `needs_listing_check`

输出 `root_classifications.json`。示意结构：

```json
{
  "asin": "B0XXXXXXXX",
  "classified_by": "ai_assistant",
  "listing_context_source": "workbook.meta.listing_context",
  "roots": {
    "portable karaoke": {
      "category": "core_category_term",
      "relevance": "high",
      "note": "与目标商品的核心用途直接一致",
      "needs_listing_check": false
    }
  },
  "term_overrides": {}
}
```

分类纪律：

1. 禁止使用 `uncertain_term`，必须给出 category 和 relevance。
2. 所有待分类词根必须覆盖，缺一个 Stage C 都会失败。
3. `needs_listing_check` 只用于少数确实依赖页面能力才能判断的词根。
4. 只有成员词明显偏离词根语义时才写 `term_overrides`。
5. 否词判断必须同时考虑相关性、样本量和 Listing 承接，不因一次点击机械否定。

## Stage C：生成正式结果

```bash
python3 skills/zach-search-term-report-analyzer/scripts/finalize_search_term_report.py \
  outputs/search-term-report-analyzer/ExampleBrand/intermediate/workbook.json \
  --classifications outputs/search-term-report-analyzer/ExampleBrand/intermediate/root_classifications.json \
  --output-dir outputs/search-term-report-analyzer/ExampleBrand/
```

Stage C 启动时会严格校验分类覆盖率和枚举值。校验通过后，每个搜索词得到一个主决策、一个决策依据层级 `basis`、置信度和原因。

## 输出

输出目录建议为 `outputs/search-term-report-analyzer/{brand}/`：

| 文件 | 用途 |
|------|------|
| `..._搜索词报告分析.md` | 主报告 |
| `..._搜索词分析明细.csv` | 全词明细 |
| `..._否词清单.csv` | exact 否词候选与 root 级 phrase 建议 |
| `..._搜索词分析操作台.html` | 可筛选、排序、勾选和导出 CSV 的交互工作台 |
| `..._搜索词分析汇报.html` | KPI、决策分布和花费去向静态汇报页 |
| `..._run_summary.json` | 验收指标与文件清单 |

两个 HTML 都是自包含单文件，数据内联，无 CDN、Webfont、外链图片或运行时 `fetch`，可直接用浏览器打开。

## 验收

读取 `run_summary.json` 并核对：

1. `pending_ratio_terms` 与 `pending_ratio_spend` 均不高于 `0.10`；超标必须解释。
2. `pool` 的词数、点击、花费和订单在报告中单独披露，且不计入 pending。
3. 六类正式输出全部存在，两个 HTML 不包含“payload 未注入”提示。
4. 决策分布、花费去向、主报告和 CSV 相互一致。
5. 报告区分数据事实与分析推断，并标注来源文件和时间范围。

## 风险与边界

- 本 skill 只输出建议，不自动修改广告预算、bid、匹配类型或否词。
- 字段不足时不强行生成 ACOS / CVR 结论；SB / SD 缺少订单或销售字段时，只做可由现有字段支持的判断并声明限制。
- ASIN 串号、产品混杂、分类覆盖不全、核心字段缺失或 pending 超标时，必须升级人工复核。
- 任何真实广告修改都应在用户确认后通过对应广告平台执行。

## 旧版兼容入口

`scripts/analyze_search_term_decisions.py` 暂时保留，供已有自动化过渡使用，但已弃用。新任务只使用 Stage A → Stage B → Stage C；旧入口将在后续大版本移除。
