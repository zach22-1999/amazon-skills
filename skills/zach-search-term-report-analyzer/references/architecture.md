# 架构契约 v2 — zach-search-term-report-analyzer

> 本文件是 v2 重建的**唯一耦合契约**：管线分工、中间产物 schema、决策规则、HTML payload 全在这里定义。
> 实现与本文件冲突时，以本文件为准；需要偏离必须显式记录。
> 重建动机：v1 没有 HTML 可视化输出，且静态词典分类与一刀切点击门槛会让大量词落入"待判定"（observe/manual_review），跑完仍需人工逐词复核。

---

## 0. 设计原则（AI 原生分工）

| 层 | 负责 | 理由 |
|---|---|---|
| **薄脚本**（Python，确定性） | 清洗、字段映射、时间窗聚合、词根聚类、指标计算、硬标签、决策规则执行、渲染输出 | 数值必须可复现、可测试 |
| **AI 助手**（语义，跑在 skill 上下文里） | 词根级语义分类 + 相关性判断（结合 Listing 上下文） | 静态词典永远盖不全长尾；语义判断是模型强项 |

**核心修复机制——词根继承**：上千长尾词按词根聚合成几十个词根；AI 助手只需分类几十个词根；点击不足的长尾词**继承词根级决策**（词根聚合后的样本量足够下结论），不再逐词落入"待判定"。

**待判定治理目标**（写进验收）：
- `待判定 = manual_review + observe(basis ∈ {term, root})`
- 目标：待判定 ≤ 10% 唯一词数 且 ≤ 10% 总花费
- `observe(basis=pool)` 是"低量长尾池"——词根样本也不足的真正碎词，**汇总监控、明确声明不逐词决策**，单独报告，不计入待判定（这是决策，不是未决）。

---

## 1. 管线总览与文件布局

```
输入报告(csv/xlsx) ──► [Stage A] prepare_search_term_analysis.py
                            │  产出 workbook.json + roots_for_review.md
                            ▼
                       [Stage B] AI 助手语义分类（读 roots_for_review.md + Listing 上下文）
                            │  产出 root_classifications.json
                            ▼
                       [Stage C] finalize_search_term_report.py
                            │  决策规则 + 渲染
                            ▼
        主报告.md + 明细.csv + 否词清单.csv + 操作台.html + 汇报.html + run_summary.json
```

```
skills/zach-search-term-report-analyzer/
  SKILL.md                        # v2 流程（重写）
  references/
    architecture.md               # 本文件（契约）
    field_mapping.md              # 保留
    decision_rules.md             # v2 重写（与本文件 §5 一致的展开版）
    term_classification.md        # v2 重写（AI 助手分类标准 + JSON schema）
    output_template.md            # v2 重写
  scripts/
    clean_search_term_report.py   # 保留复用（build_normalized_frame）
    prepare_search_term_analysis.py   # 新增 Stage A
    finalize_search_term_report.py    # 新增 Stage C
    fetch_listing_context.py      # 保留（可选工具，禁止被 A/C 顶层 import）
  assets/
    console_template.html         # 新增 操作台模板
    report_template.html          # 新增 汇报页模板
  tests/
    test_prepare.py               # 新增
    test_decisions.py             # 新增 v2 决策测试
    test_listing_context_fetch.py # 保留
    fixtures/                     # 测试夹具（小型 workbook / classifications / payload 样例）
```

**兼容保留**：`scripts/analyze_search_term_decisions.py` 与 `tests/test_decision_logic.py` 暂留一个过渡版本，公开文档不再推荐旧入口。

---

## 2. 硬约束（所有脚本）

1. 公开支持 **Python 3.10+**，命令统一使用环境中的 `python3`，不硬编码解释器绝对路径。
2. 依赖仅使用 `pandas`、`openpyxl`、`beautifulsoup4` 与标准库。Stage A / C 不导入网络模块；可选的 Listing 抓取由独立脚本和本地 `browser_utils.py` 完成。
3. 输入支持 `.csv`（utf-8 / utf-8-sig / gbk 自动探测）与 `.xlsx`（openpyxl）。
4. 数据诚信：不捏造数据；缺失字段显式声明"未使用"；报告区分「📊 数据事实」与「💡 分析推断」；除法防 0；pandas NA 全程防泄漏（比较前先 `pd.isna` 检查）。
5. 所有输出文件 UTF-8（csv 用 utf-8-sig 方便 Excel）。
6. 对外结果中的 `source_file` 只保存输入文件名，不保存本机绝对路径。

---

## 3. Stage A — prepare_search_term_analysis.py

### CLI

```
python3 prepare_search_term_analysis.py <input_file> \
  --asin B0XXXXXXXX --brand <品牌> --target-acos 0.30 [--site US] \
  [--report-type SP] [--windows 7,14,30] --output-dir <dir>
```

产出：`<output-dir>/workbook.json`、`<output-dir>/roots_for_review.md`。

### 职责

1. **清洗**：复用 `clean_search_term_report.build_normalized_frame`（若签名不适配，允许在 prepare 内重新实现等价清洗，但字段别名表必须复用 `FIELD_ALIASES`）。搜索词标准化：小写、去隐藏字符、压缩空格 → 变体归并。
2. **时间窗聚合**：以数据最大日期为锚，聚合 total / w7 / w14 / w30 每词指标：impressions, clicks, spend, orders, sales, ctr, cvr, acos, cpc。派生指标一律复算（不信报表原值），无 sales 时 acos = null。
3. **趋势标记** `trend_flag`：improving / worsening / stable / mixed / insufficient_data（w7 vs w30 CVR、ACOS 变化 > `trend_change_band` 判定；样本 <`min_clicks_for_judgement` 判 insufficient_data）。
4. **词根聚类**（确定性算法）：
   - 分词：小写、去标点（保留数字与词内连字符）；停用词表：for, with, the, a, an, of, to, in, on, and, or, my, your, best, new 等（表写在脚本常量里）。
   - 全局统计：每个 unigram 与相邻 bigram 的总点击量与出现词数（unique term count）。
   - 词根指派：对每个词，取其包含的候选 bigram 中「出现词数 ≥3」且全局点击最高者为 root_id；无合格 bigram 则取「出现词数 ≥2」点击最高的 unigram；再无则 root_id = 词本身（singleton）。
   - 词根级指标 = 成员词指标聚合（同样 total/w7/w14/w30）。
5. **硬标签**（确定性，term 级）：
   - `asin_term`：词含 `B0[A-Z0-9]{8}` 串号。
   - `brand_term`：词含本品牌 token（含 typo 模糊匹配，SequenceMatcher ≥ 0.85，逻辑可参考旧脚本 detect_term_category 的品牌分支）。
   - 硬标签词不进 needs_classification，但仍归属词根（其指标计入词根聚合）。
6. **Listing 上下文**（可选增强）：`--listing-context-file` 传入 md/txt 时读入并放进 workbook.meta，供 Stage B 使用；不传不报错。

### workbook.json schema

```jsonc
{
  "meta": {
    "generated_at": "YYYY-MM-DD HH:MM",
    "source_file": "...", "brand": "...", "asin": "...",
    "report_type": "SP", "site": "US", "target_acos": 0.30,
    "date_range": ["YYYY-MM-DD", "YYYY-MM-DD"],
    "windows": [7, 14, 30],
    "baseline": {"clicks": 0, "spend": 0.0, "orders": 0, "sales": 0.0, "cvr": null, "acos": null},
    "has_orders_data": true,          // 报表是否含订单/销售字段
    "listing_context": "...|null",
    "thresholds": { /* §5 阈值表实际取值 */ },
    "unused_fields": ["..."]
  },
  "terms": [{
    "search_term": "...", "root_id": "...",
    "match_types": ["BROAD"],
    "hard_tag": null,                  // null | "brand_term" | "asin_term"
    "metrics": {
      "total": {"impressions":0,"clicks":0,"spend":0.0,"orders":0,"sales":0.0,"ctr":null,"cvr":null,"acos":null,"cpc":null},
      "w7": {...}, "w14": {...}, "w30": {...}
    },
    "trend_flag": "stable"
  }],
  "roots": [{
    "root_id": "...", "term_count": 0,
    "sample_terms": ["按点击 top8"],
    "metrics": { "total": {...}, "w7": {...}, "w14": {...}, "w30": {...} },
    "hard_tag": null,                  // 若全部成员同为 brand/asin 硬标签
    "needs_classification": true       // 无硬标签的词根为 true
  }],
  "classification_request": {
    "schema_pointer": "references/term_classification.md",
    "roots_to_classify": ["root_id..."],
    "top_terms_for_override": ["按花费 top30 的词"]   // 建议 AI 助手顺带检查是否需要 term 级 override
  }
}
```

### roots_for_review.md 格式

供 AI 助手（或人）快速分类的表格：每行一个待分类词根——root_id、成员词数、样本词（top5）、total 点击/花费/订单/CVR/ACOS。按花费降序。文件头部写明分类任务说明与 root_classifications.json 的写法示例。

---

## 4. Stage B — AI 助手语义分类（root_classifications.json）

AI 助手读 `roots_for_review.md` + Listing 上下文（workbook.meta.listing_context / 本地快照 / 前台抓取），产出：

```jsonc
{
  "asin": "...", "classified_by": "ai_assistant", "listing_context_source": "...",
  "roots": {
    "<root_id>": {
      "category": "core_category_term",   // 见下方枚举
      "relevance": "high",                // high | medium | low（与本 ASIN 的相关度）
      "note": "一句话依据",
      "needs_listing_check": false         // 仅极少数真拿不准时 true → manual_review
    }
  },
  "term_overrides": {                      // 可选：个别词偏离词根语义时点名覆盖
    "<search_term>": {"category": "competitor_term", "relevance": "low", "note": "..."}
  }
}
```

**category 枚举**：`brand_term` / `competitor_term` / `core_category_term` / `attribute_term` / `scenario_term` / `irrelevant_term` / `asin_term`。

**纪律**：
1. **禁止 uncertain**——必须给出 category + relevance；真拿不准的用 `needs_listing_check: true` 标记（应极少，>5% 即算分类失职）。
2. `classification_request.roots_to_classify` 中每个词根**必须**有条目——finalize 严格校验，缺项即报错退出（fail loud）。
3. relevance 定义：high = 本 ASIN 能直接承接该需求；medium = 部分承接/边缘变体；low = 基本不承接。
4. 竞品判断可用报表内高频前导品牌 token + 常识品牌知识；无关判断结合 Listing 卖点。

---

## 5. Stage C — finalize_search_term_report.py

### CLI

```
python3 finalize_search_term_report.py <workbook.json> \
  --classifications <root_classifications.json> --output-dir <dir> \
  [--report-title-prefix "YYYY-MM-DD_品牌_ASIN"]
```

启动即严格校验 classifications 覆盖率与 category 枚举，缺失/非法即列明细并 exit 1。

### 阈值（沿用 v1 + 新增，集中为脚本常量，禁散写）

```yaml
min_clicks_for_judgement: 8        # term 级样本门槛
root_min_clicks_for_judgement: 12  # root 级样本门槛（新增）
min_clicks_for_priority: 15
min_clicks_for_scale_up: 12
min_spend_for_attention: 10.0
high_spend_without_orders: 15.0
near_avg_cvr_band: 0.15
high_cvr_band: 0.20
low_cvr_band: 0.20
trend_change_band: 0.20
max_target_acos_multiple_for_scale_up: 1.15
very_high_target_acos_multiple: 1.50
negative_min_clicks: 2             # 无关词进否词的最低点击（新增）
negative_min_spend: 1.0            # 或最低花费（新增）
```

### 决策算法（有序，每词恰好一个主 decision + basis + confidence + reason）

```
effective_category(term) = hard_tag ➜ term_override ➜ root.category
effective_relevance     = 同优先级；brand/asin 视为 high

sample_basis(term):
  term.total.clicks >= min_clicks_for_judgement            → basis=term,  m=term.total
  elif root.total.clicks >= root_min_clicks_for_judgement  → basis=root,  m=root.total
  else                                                     → basis=pool

decide(term)（依序命中即返回）:
 1. category==asin_term → manual_review「ASIN 串号词，人工判断承接来源」
 2. needs_listing_check（来自分类）→ manual_review
 3. category==brand_term:
    - term 0 单且 spend>=high_spend_without_orders → manual_review「品牌词高耗0单，查承接页」
    - 否则 hold_test「品牌承接/防守，保持」（bucket=brand，报告单列）
 4. category==competitor_term:
    - 0 单且 spend>=high_spend_without_orders → reduce_bid「竞品词高耗无单，先控」
    - basis≠pool 且 cvr<=baseline*(1-low_cvr_band) → reduce_bid
    - 其余 → hold_test「竞品词表现尚可，加码属策略决策」（bucket=competitor，单列）
 5. category==irrelevant_term:
    - clicks>=negative_min_clicks 或 spend>=negative_min_spend → negative_candidate（建议 negative exact；
      若整词根 irrelevant 且 term_count>=3 → 汇总另建 root 级 negative phrase 建议）
    - 否则 → observe(basis=pool)（进低量池）
 6. （相关类：core/attribute/scenario）basis==pool → observe(basis=pool)（低量池，汇总监控）
 7. 用 m（term 或 root 指标）判：
    a. has_orders_data==false（SB/SD 无订单报表）→ 只做浪费检测：
       spend>=high_spend_without_orders → reduce_bid；否则 hold_test；报告声明局限
    b. cvr >= baseline*(1+high_cvr_band):
       - basis==term 且 clicks>=min_clicks_for_scale_up 且 acos<=target*max_scale_mult → scale_up
       - acos 超标 → reduce_bid「高转化但成本超标，压 bid 等 CPC 回落」
       - basis==root → hold_test「词根整体高效，小步提 bid 测试」
    c. baseline*(1-near_band) <= cvr <= baseline*(1+near_band):
       acos>target → reduce_bid；否则 hold_test
    d. cvr <= baseline*(1-low_cvr_band):
       - 0 单且(spend>=high_spend_without_orders 或 clicks>=min_clicks_for_priority):
         relevance==high 且 attr/scen 且 listing 未覆盖 → listing_feedback（广告侧同时给控bid注）
         relevance==high → reduce_bid「相关但转化不达标，控成本+查承接」
         其余 → negative_candidate「低相关低效，止损」
       - acos>target*very_high_mult → reduce_bid
       - relevance==low → negative_candidate
       - 其余 → reduce_bid「低于基准，先小步降bid」
    e. 其余（介于带间）→ hold_test
 8. 兜底（理论不可达）→ hold_test（**禁止兜底 observe**）
降级规则：trend_flag==mixed 且结果为 scale_up → 降为 hold_test「窗口信号打架，先稳」
listing_feedback 附加位：attr/scen + w7 点击上升 + Listing 未覆盖 → 独立 flag（不占主 decision，除 7d 命中外）
confidence：basis==term 且 clicks>=15 → high；basis==term 或 root_clicks>=20 → medium；其余 low
```

### 验收指标（run_summary.json 必含，超标不失败但显式告警）

- `pending_ratio_terms` / `pending_ratio_spend`（待判定占比，目标 ≤0.10）
- `pool` 统计（词数/点击/花费/订单）
- 决策/类别分布计数与花费分布

### 输出文件（--output-dir 下，前缀 `{date}_{brand}_{asin}`）

| 文件 | 说明 |
|---|---|
| `..._搜索词报告分析.md` | 主报告（YAML 元数据头 + 结论摘要 + 各决策分节表 + 数据事实/推断标注） |
| `..._搜索词分析明细.csv` | 全词明细（列见 payload.terms 字段） |
| `..._否词清单.csv` | search_term, match_type(negative exact/phrase), reason, spend, clicks（root 级 phrase 建议单独段） |
| `..._搜索词分析操作台.html` | console_template.html 注入 payload |
| `..._搜索词分析汇报.html` | report_template.html 注入 payload |
| `..._run_summary.json` | 验收指标 + 文件清单 |

---

## 6. HTML 契约

### 注入机制

模板内固定占位：`<script id="payload" type="application/json">__PAYLOAD_JSON__</script>`。
finalize 用字符串替换注入 `json.dumps(payload, ensure_ascii=False)`，注入前把 `</` 转义为 `<\/`（防 `</script>` 提前闭合）。模板 JS 里 `JSON.parse(document.getElementById('payload').textContent)`；解析失败或占位未替换时页面显示「payload 未注入」提示而非白屏。

### payload schema

```jsonc
{
  "meta": { /* = workbook.meta + {run_at} */ },
  "summary": {
    "decision_counts": {"scale_up":0,"hold_test":0,"reduce_bid":0,"negative_candidate":0,"listing_feedback":0,"observe":0,"manual_review":0},
    "decision_spend": { /* 同键，花费 */ },
    "category_counts": {}, "category_spend": {},
    "pending_ratio_terms": 0.0, "pending_ratio_spend": 0.0,
    "pool": {"terms":0,"clicks":0,"spend":0.0,"orders":0},
    "waste": {"zero_order_spend":0.0,"negative_candidate_spend":0.0},
    "baseline": {"cvr":null,"acos":null,"clicks":0,"spend":0.0,"orders":0}
  },
  "terms": [{
    "term":"","category":"","relevance":"","decision":"","confidence":"","basis":"term|root|pool",
    "reason":"","root":"","match_types":[],
    "clicks":0,"spend":0.0,"orders":0,"sales":0.0,"cvr":null,"acos":null,"cpc":null,"ctr":null,
    "w7":{"clicks":0,"cvr":null,"acos":null},"w14":{...},"w30":{...},
    "trend":"","listing_flag":false,"negative_match_suggestion":null
  }],
  "roots": [{"root":"","category":"","relevance":"","term_count":0,"clicks":0,"spend":0.0,"orders":0,"cvr":null,"acos":null,"sample_terms":[]}],
  "actions": {
    "negatives":[{"term":"","match_type":"negative exact","reason":"","spend":0.0,"clicks":0}],
    "root_negatives":[{"root":"","match_type":"negative phrase","reason":"","term_count":0,"spend":0.0}],
    "scale_ups":[{"term":"","reason":"","clicks":0,"cvr":null,"acos":null}],
    "reduce_bids":[{"term":"","reason":"","spend":0.0,"acos":null}],
    "listing_feedback":[{"term":"","insight":"","suggestion":""}],
    "manual_review":[{"term":"","reason":""}]
  }
}
```

### 操作台 console_template.html（交互工作台，给运营人员做决策落地）

- 顶部摘要卡：总花费 / 浪费花费 / 否词数 / 放量数 / 待判定占比 / 低量池规模 / 基准 CVR·ACOS
- 主表格：payload.terms 全量；列 = 词/类别/决策/置信度/依据(basis)/点击/花费/订单/CVR/ACOS/趋势/理由
- 交互：决策 tab 筛选（全部/否词/放量/降bid/Listing反馈/品牌/竞品/待判定/低量池）、类别下拉、文本搜索、任意列排序、行勾选
- 导出：「导出否词清单 CSV」「导出放量清单 CSV」「导出勾选行 CSV」——JS Blob 下载，CSV 字段正确转义（逗号/引号/换行）
- 词根视图 tab：payload.roots 表
- 低量池折叠展示（默认收起，标注"汇总监控，不逐词决策"）
- 中文 UI；系统字体栈；**零外部资源**（无 CDN/webfont/外链图）；单文件自包含

### 汇报页 report_template.html（静态结论页，可给团队/汇报）

- 结论优先：KPI 卡 → 决策分布横条图（纯 CSS/inline SVG）→ 花费去向（类别×决策）→ TOP10 否词表 → TOP10 放量表 → 属性/场景洞察（listing_feedback）→ 趋势要点 → 方法论脚注（词根继承机制一句话说明 + 数据来源与时间范围）
- 「📊 数据事实」与「💡 分析推断」视觉区分；print 友好（@media print）；零外部资源

---

## 7. SKILL.md v2 流程骨架（Stage 编排）

1. Step 0 信息收集：报告文件、ASIN、品牌、目标 ACOS；四项都必须显式提供
2. Step 1 跑 prepare → 得 workbook.json + roots_for_review.md
3. Step 2 AI 助手分类：读 roots_for_review.md + Listing 上下文（本地快照优先，必要时 fetch_listing_context / 前台），写 root_classifications.json（严格按 term_classification.md schema，禁 uncertain）
4. Step 3 跑 finalize → 六件套输出
5. Step 4 验收自检：读 run_summary.json，报告待判定占比 vs 目标；超标要解释原因；输出 3 句话摘要 + 文件路径
6. 输出目录：`outputs/search-term-report-analyzer/{brand}/`
