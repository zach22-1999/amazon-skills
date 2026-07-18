# 搜索词决策规则（v2 · 解释层）

> **权威定义见 `architecture.md` §5，本文件是解释层**：面向运营，讲清每条规则的业务理由。
> 实现（`finalize_search_term_report.py`）与本文件冲突时，以 `architecture.md` 为准，并回头修订本文件。

---

## 1. v2 决策的三个底座

### 1.1 基准 = 本 ASIN 自身的广告 CVR

`基准CVR = 该 ASIN 分析窗口内总订单数 / 总点击量`。不用全店平均、不用全报告平均——不同产品的转化天花板差异太大，只有和自己比才能回答"这个词对**这个产品**是好是坏"。注意口径：广告 CVR = orders/clicks，禁止与业务 CVR（orders/sessions）互比（见 Ontology Bridge 9）。

### 1.2 词根继承（sample_basis）——治"待判定"的核心机制

v1 的病根：一刀切点击门槛（点击 < 8 就不下结论），导致上千长尾词全部落入"待判定"，跑完还得人工再判一遍。v2 的解法是三级样本依据：

| basis | 条件 | 含义 |
|---|---|---|
| `term` | 该词自身点击 ≥ 8（`min_clicks_for_judgement`） | 词自己的样本够，用词自己的指标判 |
| `root` | 词样本不足，但所属词根总点击 ≥ 12（`root_min_clicks_for_judgement`） | **长尾词继承词根级决策**——词根聚合后的样本量足够下结论 |
| `pool` | 词根样本也不足 | 真正的碎词，进"低量长尾池"：汇总监控、明确声明不逐词决策 |

业务理由：`karaoke machine for kids with 2 mics pink` 这种词一个月可能只有 3 次点击，单看它永远"数据不足"；但它所属的词根（如 `for kids`）聚合了 40 个成员词、200 次点击，词根层面完全够下结论——长尾词没必要各自为战。`pool` 是一种决策（"这堆碎词不值得逐词管理"），不是未决，所以不计入待判定。

### 1.3 类别与相关性来自 AI 助手语义分类，不再靠静态词典

```
effective_category(term) = 硬标签(hard_tag) ➜ term 级覆盖(term_override) ➜ 词根分类(root.category)
effective_relevance     = 同优先级取值；brand/asin 视为 high
```

硬标签（品牌词 / ASIN 串号词）是脚本确定性识别的，优先级最高；AI 助手对花费 top30 的词可以做 term 级覆盖（个别词偏离词根语义时点名纠正）；其余词一律继承词根的 category / relevance。静态词典永远盖不全长尾，语义判断交给模型，数值判断留给脚本。

---

## 2. 阈值表与业务理由

阈值集中为 `finalize_search_term_report.py` 的脚本常量（禁散写），实际取值同时写进 workbook.meta.thresholds：

| 阈值 | 默认值 | 业务理由 |
|---|---|---|
| `min_clicks_for_judgement` | 8 | term 级样本门槛：8 次点击以下，单词 CVR 波动太大，不用词自身指标下结论 |
| `root_min_clicks_for_judgement` | 12 | root 级样本门槛（v2 新增）：词根是聚合值，要求比 term 略高才有代表性 |
| `min_clicks_for_priority` | 15 | 点击到这个量级的词对预算影响直接，优先进处理名单 |
| `min_clicks_for_scale_up` | 12 | 放量是加钱动作，比一般判断要求更多样本，防止对偶然高 CVR 加仓 |
| `min_spend_for_attention` | 10.0 | 点击不高但钱已经花出去了，也要进入关注 |
| `high_spend_without_orders` | 15.0 | 0 单词的止损线：花到这个数还没单，即使 ACOS 因无销售额缺失也要动手 |
| `near_avg_cvr_band` | 0.15 | 与基准差 ±15% 内视为"接近平均"——广告数据噪音大，太窄的带会频繁误判 |
| `high_cvr_band` | 0.20 | 高于基准 20% 以上才算"明显高于平均"，够格谈放量 |
| `low_cvr_band` | 0.20 | 低于基准 20% 以上才算"明显低于平均"，够格谈控成本/否定 |
| `trend_change_band` | 0.20 | 窗口间指标变化超 20% 才算趋势显著，过滤日常波动 |
| `max_target_acos_multiple_for_scale_up` | 1.15 | 放量红线：ACOS 超目标 15% 以上时，CVR 再高也不加码 |
| `very_high_target_acos_multiple` | 1.50 | ACOS 超目标 50% 是硬伤，直接进控 bid，不再观察 |
| `negative_min_clicks` | 2 | 无关词进否词的最低点击（v2 新增）：0/1 次点击的无关词否掉性价比低，先进低量池 |
| `negative_min_spend` | 1.0 | 或最低花费（v2 新增）：钱已实际浪费的无关词，点击再少也否 |

---

## 3. 决策规则逐条解释（按命中顺序，每词恰好一个主决策）

规则**有序**执行，命中即返回。每个词最终带四件套：decision + basis + confidence + reason。

### 规则 1 — ASIN 串号词 → `manual_review`

词里含 `B0XXXXXXXX` 串号的，可能是品牌承接、竞品流量或用户直搜 ASIN，语义无法自动分辨，固定升级人工。这是待判定里**合理存在**的部分。

### 规则 2 — 分类标记 needs_listing_check → `manual_review`

AI 助手分类时极少数真拿不准的词根（应 <5%），尊重标记升级人工。

### 规则 3 — 品牌词：防守逻辑，不做常规效率判断

- term 级 0 单且花费 ≥ 15 → `manual_review`「品牌词高耗 0 单，查承接页」——自己的品牌词都不转化，大概率是 Listing/承接出了问题，不是流量问题。
- 其余 → `hold_test`「品牌承接/防守，保持」。品牌词承担防守职能，CVR 高不代表泛品类需求扩张，CVR 一般也不轻易撤——单列 brand bucket，在报告里与泛词分开看。

### 规则 4 — 竞品词：抢量是策略决策，脚本只做止损

- 0 单且花费 ≥ 15 → `reduce_bid`「竞品词高耗无单，先控」。
- 有样本（basis≠pool）且 CVR 明显低于基准 → `reduce_bid`。
- 其余 → `hold_test`「竞品词表现尚可，加码属策略决策」——要不要跟某个竞品打，是更高层的策略判断，skill 只保证不流血，单列 competitor bucket。

### 规则 5 — 无关词：达到最低量就进否词，碎词进池

- 点击 ≥ 2 或花费 ≥ $1 → `negative_candidate`（建议 negative exact）。**整个词根都无关且成员 ≥ 3 个词时，额外给 root 级 negative phrase 建议**——一条 phrase 否词顶几十条 exact，这是词根聚合在否词侧的红利。
- 量不够的 → `observe(basis=pool)` 进低量池。否掉一个从没花过钱的词没有收益，还占否词位。

### 规则 6 — 相关词但词和词根样本都不足 → `observe(basis=pool)`

core / attribute / scenario 类词，basis==pool 时进低量池汇总监控。这是声明"不逐词决策"，不是拖延。

### 规则 7 — 相关词的效率判断（用 term 或 root 指标 m）

**7a. 报表无订单数据**（SB/SD 部分报表）：只做浪费检测——花费 ≥ 15 → `reduce_bid`，否则 `hold_test`，并在报告显式声明"无订单字段，无法做 CVR/ACOS 判断"的局限。没有数据就不硬给结论。

**7b. CVR 明显高于基准（≥ 基准×1.2）**：
- basis==term 且点击 ≥ 12 且 ACOS ≤ 目标×1.15 → `scale_up`——三个条件缺一不可：真实高效 + 样本够 + 成本可控。
- ACOS 超标 → `reduce_bid`「高转化但成本超标，压 bid 等 CPC 回落」——词是好词，问题在出价。
- basis==root（继承）→ `hold_test`「词根整体高效，小步提 bid 测试」——继承的信号不足以直接加仓单个词，但值得试。

**7c. CVR 接近基准（±15% 带内）**：看 ACOS 定方向——超目标 → `reduce_bid`（词不差，成本压力偏高）；不超 → `hold_test`（保持或小幅测试放量空间）。

**7d. CVR 明显低于基准（≤ 基准×0.8）**：
- 0 单且（花费 ≥ 15 或点击 ≥ 15）——已经形成实际浪费：
  - relevance==high 且属性/场景词且 Listing 未覆盖 → `listing_feedback`——词有真实需求但页面没承接，这是产品/内容问题不是流量问题，否掉可惜（广告侧同时给控 bid 注记）。
  - relevance==high → `reduce_bid`「相关但转化不达标，控成本+查承接」——相关词不轻易否，先控成本查承接。
  - 其余 → `negative_candidate`「低相关低效，止损」。
- ACOS > 目标×1.5 → `reduce_bid`——严重超标直接动手。
- relevance==low → `negative_candidate`——低相关+低效，双重确认可以否。
- 其余 → `reduce_bid`「低于基准，先小步降 bid」——渐进处理，不一步否死。

### 规则 7e / 8 — 带间词与兜底 → `hold_test`

CVR 落在"明显高"与"明显低"之间未被前面命中的 → `hold_test`。兜底（理论不可达）也是 `hold_test`——**禁止兜底 observe**：v1 的教训就是把"不知道怎么办"都堆进 observe，v2 规定除低量池外不允许产生 observe。

### 降级规则 — 趋势打架时收紧放量

`trend_flag==mixed`（7/14/30 天窗口信号互相冲突）且结果为 `scale_up` → 降为 `hold_test`「窗口信号打架，先稳」。加钱动作必须建立在稳定信号上；控成本动作不受此限（止损不用等趋势确认）。

### listing_feedback 附加位

属性/场景词 + 近 7 天点击上升 + Listing 未覆盖 → 独立 flag（不占主 decision，除 7d 命中外）。广告决策和内容反馈是两条线，一个词可以既"降 bid"又"值得反馈给 Listing"。

### confidence 三级

- `high`：basis==term 且点击 ≥ 15——词自己的数据充分。
- `medium`：basis==term（8–14 次点击）或词根点击 ≥ 20 的继承决策。
- `low`：其余——主要是刚过 root 门槛的继承决策。执行时 low 置信度的动作建议幅度放小。

---

## 4. 待判定治理与验收口径

- `待判定 = manual_review + observe(basis ∈ {term, root})`；**pool 不计入**（它是明确的"汇总监控"决策）。
- 目标：待判定 ≤ 10% 唯一词数 **且** ≤ 10% 总花费。`run_summary.json` 输出 `pending_ratio_terms` / `pending_ratio_spend`，超标不失败但显式告警，报告里必须解释原因。
- 合理的待判定来源基本只有：ASIN 串号词（规则 1）、needs_listing_check（规则 2）、品牌词高耗 0 单（规则 3）。若超标且不来自这三处，先检查分类质量。

## 5. 报告输出优先级

1. `negative_candidate`（先止血）
2. `scale_up`（再抓机会）
3. `reduce_bid`（控成本）
4. `listing_feedback`（需协同的认知反馈）
5. brand / competitor bucket（策略参考）
6. `manual_review`（人工项）
7. `observe(pool)`（低量池，折叠汇总）

先处理浪费，再处理机会，再处理协同，最后才是观察项——和钱的关系越直接，排得越靠前。
