# 搜索词语义分类操作指南（v2 · Stage B / AI 助手执行）

> 本文件是 **Stage B 的操作标准**：AI 助手读 `roots_for_review.md` + Listing 上下文，按本文件产出 `root_classifications.json`。
> schema 与纪律的权威定义见 `architecture.md` §4；冲突时以 architecture.md 为准。
> v2 与 v1 的关键区别：分类粒度从"逐词"改为"**词根级**"（几十个词根，不是上千个词）；静态词典废弃，由 AI 助手做语义判断；**不再有 `uncertain_term`**。

---

## 1. 分类对象与粒度

- **主对象**：`workbook.json` 的 `classification_request.roots_to_classify` 中的每个词根。带硬标签（brand/asin）的词根脚本已确定性识别，不在待分类清单里。
- **辅对象**：`classification_request.top_terms_for_override`（按花费 top30 的词）——逐个检查是否偏离所属词根的语义；偏离时写 `term_overrides` 点名覆盖，不偏离就不写。
- 判断依据：词根的样本词（sample_terms）+ 成员词数 + 核心指标（点击/花费/订单/CVR/ACOS）+ Listing 上下文 + 报表内高频前导品牌 token + 常识品牌知识。

## 2. category 枚举定义与判例

每个词根恰好一个 category，取值只能是以下 7 个（以卡拉 OK 机为例品）：

| category | 定义 | 判例（属于） | 判例（不属于） |
|---|---|---|---|
| `brand_term` | 含本品牌名、简称、拼写变体 | `examplebrand machine`、`examplbrand`（typo） | 竞品品牌（→ competitor_term） |
| `competitor_term` | 含竞品品牌名、系列名、代表性型号 | `rivalbrand karaoke`、`rivalbrand microphone` | 拿不准是不是品牌的普通词（按语义归入其他类） |
| `core_category_term` | 直接描述核心品类，无明显属性/场景限定 | `karaoke machine`、`karaoke system` | `portable karaoke machine`（→ attribute_term） |
| `attribute_term` | 描述规格、功能、配置、材质、颜色、尺寸等属性 | `with 2 microphones`、`bluetooth`、`with screen` | 纯人群/场合词（→ scenario_term） |
| `scenario_term` | 描述使用场景、人群、目的、礼品需求、场所 | `for adults`、`party`、`gift for kids` | 属性限定（→ attribute_term） |
| `irrelevant_term` | 与本 ASIN 的核心功能、卖点、目标人群明显不匹配 | 卖家用机器收到 `car karaoke decoration` | 本品未覆盖但品类相关的属性词（→ attribute_term + relevance 降级） |
| `asin_term` | 含 `B0XXXXXXXX` ASIN 串号 | `b0abc123de karaoke` | —（脚本通常已硬标签，剩余的照实标） |

多类别同时命中时的主标签优先级（从高到低）：

1. `brand_term` → 2. `competitor_term` → 3. `asin_term` → 4. `irrelevant_term` → 5. `attribute_term` → 6. `scenario_term` → 7. `core_category_term`

例：`rivalbrand karaoke for party` 同时命中竞品与场景，主标签取 `competitor_term`。

**注意区分 category 与 relevance**：一个词是不是无关（category），和本品能不能承接（relevance）是两个维度。`karaoke machine with lyrics screen` 对无屏机型不是 `irrelevant_term`（它是真实的品类内属性需求），而是 `attribute_term` + `relevance: low`——这个区分直接决定该词走"否定"还是"控成本/反馈 Listing"。

## 3. relevance 三级定义

回答"**本 ASIN** 能不能承接这个需求"，必须结合 Listing 上下文判：

| relevance | 定义 | 例（无屏便携卡拉 OK 机） |
|---|---|---|
| `high` | 本 ASIN 能直接承接该需求 | `portable karaoke machine`、`karaoke for party` |
| `medium` | 部分承接 / 边缘变体：需求沾边但不是本品主打 | `karaoke machine for car`（能用但非设计场景） |
| `low` | 基本不承接：品类相关但本品没有该属性/不面向该人群 | `karaoke machine with screen`（本品无屏） |

`brand_term` / `asin_term` 在决策层视为 high，不必纠结。

## 4. root_classifications.json schema 与示例

与 `workbook.json` 同目录写入，结构（权威版见 architecture.md §4）：

```jsonc
{
  "asin": "B0XXXXXXXX",
  "classified_by": "ai_assistant",
  "listing_context_source": "workbook.meta / 本地快照路径 / fetch_listing_context / 前台抓取",
  "roots": {
    "<root_id>": {
      "category": "core_category_term",   // §2 的 7 个枚举之一
      "relevance": "high",                // high | medium | low
      "note": "一句话依据",
      "needs_listing_check": false        // 仅极少数真拿不准时 true → manual_review
    }
  },
  "term_overrides": {                     // 可选：个别词偏离词根语义时点名覆盖
    "<search_term>": {"category": "competitor_term", "relevance": "low", "note": "..."}
  }
}
```

填写示例：

```json
{
  "asin": "B0ABC12345",
  "classified_by": "ai_assistant",
  "listing_context_source": "examples/listing-context-sample.md",
  "roots": {
    "karaoke machine": {"category": "core_category_term", "relevance": "high", "note": "核心品类词，本品直接承接", "needs_listing_check": false},
    "for kids": {"category": "scenario_term", "relevance": "medium", "note": "本品面向成人聚会，儿童场景为边缘承接", "needs_listing_check": false},
    "with screen": {"category": "attribute_term", "relevance": "low", "note": "品类内真实属性需求，但本品无屏不承接", "needs_listing_check": false},
    "rivalbrand": {"category": "competitor_term", "relevance": "low", "note": "报表内高频前导品牌 token，作为竞品品牌处理", "needs_listing_check": false}
  },
  "term_overrides": {
    "karaoke machine rental": {"category": "irrelevant_term", "relevance": "low", "note": "租赁需求，非购买意图，与词根 karaoke machine 语义偏离"}
  }
}
```

## 5. 四条纪律（硬约束）

1. **禁止 uncertain**。每个词根必须给出 category + relevance，没有"暂不确定"这个出口。真拿不准的用 `needs_listing_check: true` 标记（进 manual_review），但这应当**极少**——超过词根数 5% 即算分类失职，先回去补 Listing 上下文再分类。
2. **全覆盖**。`classification_request.roots_to_classify` 中每个词根必须有条目——`finalize` 严格校验覆盖率与枚举合法性，缺项/非法即列明细报错退出（fail loud）。宁可给出有依据的判断，不许留空。
3. **needs_listing_check 少用**。它是逃生口不是分类项；每标一个都要问自己：拿到 Listing 上下文了吗？拿到了还标，就要在 note 里写清到底缺什么信息。
4. **无关判断必须结合 Listing**。`irrelevant_term` 和 `relevance: low` 都是"结合本品卖点"的结论，不是词面直觉。判无关前必须已读 Listing 上下文（标题/卖点/描述）；上下文缺失时先取（本地快照 → `fetch_listing_context.py` → 前台），不许凭空判无关——错判无关 = 错否词 = 直接砍掉真实流量。

## 6. 竞品词判断的依据来源

- 报表内高频**前导品牌样式 token**（多个搜索词以同一非本品牌 token 开头，且该 token 不是通用词）；
- 常识品牌知识（明确知道的竞品品牌/系列/型号）；
- 拿不准某 token 是否品牌时，不标 competitor_term，按词面语义归入其他类——竞品误判的代价（错误 hold 一个本可正常判断的词根）低于无关误判，但也不要滥标。
