---
name: zach-feature-demand-validator
description: 功能需求真伪验证器。在产品开发决策前，用三维数据（Review 信号、关键词信号、社区信号）验证某个新功能/细分功能是真实市场需求还是伪需求。使用时机：品类选定后评估微创新是否值得投入、竞品分析中发现功能差异点后判断要不要跟进。
---

## 定位

亚马逊卖家的产品开发，大多数时候不是做颠覆式创新，而是在现有供给上做微创新：

- 加一个小功能
- 补一个小结构
- 优化一个小体验

危险点也恰好在这里。很多功能看起来合理，但很可能只是卖家自己的想象，不是消费者真实在意的点。

这个 Skill 的定位，不是帮你发明新物种，而是判断：

**这个微创新，到底是不是用户真的在意。**

它通过三个独立维度交叉验证，避免“感觉有需求就开模”。

| 维度 | 首选数据源 | 无 Sorftime 时的处理 |
|------|-----------|-------------------|
| Review 信号 | Sorftime `product_reviews` | 允许降级到 `review_source_pack` 手动证据包 |
| 关键词信号 | Sorftime `keyword_detail` / `keyword_trend` / `keyword_extends` | 明确标记为未验证，不伪造数据 |
| 社区信号 | WebSearch（Reddit + Quora） | 继续可执行 |

## 上游 / 下游

- **上游**：`zach-product-research`、`zach-competitor-deep-dive`
- **下游**：`zach-new-product-listing-writer`

---

## 执行优先级

### 路线 A：Sorftime 完整版

适用条件：当前环境可调用 Sorftime MCP。

1. Review 维度走 Sorftime `product_reviews`
2. 关键词维度走 Sorftime 关键词工具
3. 社区维度走 WebSearch

### 路线 B：Sorftime 缺失时的降级版

适用条件：当前环境没有 Sorftime MCP，或者用户明确只提供了本地评论证据。

1. Review 维度改用 `review_source_pack`
2. 关键词维度写明“未验证 / 待补充”
3. 社区维度继续走 WebSearch

**注意**：降级版不是完整版。它只能先回答“评论里到底有没有人在乎这个功能”，不能替代关键词需求验证。

---

## 输入方式

### 业务输入

支持两类：

| 输入方式 | 示例 | 处理逻辑 |
|---------|------|---------|
| 品类 + 功能描述 | `air fryer + steam feature` | 先找市场上是否已有带该功能的产品 |
| ASIN + 功能描述 | `B0XXXX + self-cleaning` | 直接围绕指定产品和相邻竞品验证 |

默认站点：`US`

### Review fallback 输入

当 Sorftime 不可用时，用户需要提供本地评论证据包：

```text
review_source_pack/
├── source_manifest.json
└── raw/
    ├── reviews.csv
    ├── reviews.txt
    └── reviews.html
```

详细格式见 `references/review_fallback_pack.md`。

---

## 执行流程

### Step 0：解析任务与构造关键词

1. 确认输入是“品类 + 功能”还是“ASIN + 功能”
2. 确认站点，默认 `US`
3. 基于 `references/keyword_construction_guide.md` 构造 3-5 个英文关键词变体
4. 判断当前走 Sorftime 完整版还是 Review fallback 降级版

### Step 1：Review 信号采集

#### 1.1 Sorftime 完整版

1. 若用户给的是品类：
   - 调 `product_search` 找含该功能的产品
   - 优先选 3-5 个月销高、评论多、标题明确带功能词的 ASIN
2. 若用户给的是 ASIN：
   - 直接用该 ASIN
   - 必要时调 `product_detail` 确认功能是否真实存在
3. 对每个目标 ASIN 调 `product_reviews`
4. 把返回结果保存为 JSON，再调用脚本：

macOS / Linux:
```bash
python3 skills/zach-feature-demand-validator/scripts/parse_reviews.py \
  --input <reviews.json> \
  --asin <ASIN> \
  --keywords "steam,steamer,steaming" \
  --source-url "sorftime://product_reviews/<ASIN>" \
  --output <数据源目录>/01_review_信号_原始数据.csv
```

Windows:
```powershell
py -3 skills/zach-feature-demand-validator/scripts/parse_reviews.py `
  --input <reviews.json> `
  --asin <ASIN> `
  --keywords "steam,steamer,steaming" `
  --source-url "sorftime://product_reviews/<ASIN>" `
  --output <数据源目录>\01_review_信号_原始数据.csv
```

#### 1.2 Review fallback 降级版

1. 要求用户提供 `review_source_pack/`
2. 检查 `source_manifest.json` 是否包含 ASIN、站点、导出时间、来源 URL、导出方式
3. 调脚本统一解析原始证据：

macOS / Linux:
```bash
python3 skills/zach-feature-demand-validator/scripts/parse_review_source_pack.py \
  --pack <review_source_pack> \
  --keywords "steam,steamer,steaming" \
  --output <数据源目录>/01_review_信号_原始数据.csv
```

Windows:
```powershell
py -3 skills/zach-feature-demand-validator/scripts/parse_review_source_pack.py `
  --pack <review_source_pack> `
  --keywords "steam,steamer,steaming" `
  --output <数据源目录>\01_review_信号_原始数据.csv
```

支持的原始文件格式：

- `CSV`
- `TXT` / `Markdown`
- `HTML`

#### 1.3 Review 判定

判定标准见 `references/judgment_criteria.md`，核心仍是：

- 功能提及率
- 需求表达数（如 `wish it had`）
- 正负反馈分布

### Step 2：关键词信号采集

#### 2.1 有 Sorftime 时

对关键词变体依次调用：

- `keyword_detail`
- `keyword_trend`
- `keyword_extends`

再用脚本导出标准 CSV：

```bash
python3 skills/zach-feature-demand-validator/scripts/generate_keyword_csv.py \
  --type detail \
  --data <detail.json> \
  --source-ref "keyword_detail:steam air fryer" \
  --output <数据源目录>/02_keyword_信号_搜索量数据.csv
```

#### 2.2 无 Sorftime 时

- 关键词维度不得伪造
- 报告中明确写：`[数据缺口] 当前环境无 Sorftime MCP，本次未完成关键词信号验证`
- `02/03/04` 三个 CSV 仍需保留，但内容可为 `N/A + 数据缺口说明`

### Step 3：社区信号采集

1. 用 WebSearch 搜索 Reddit / Quora
2. 保留标题、URL、发布日期、态度摘要、查询词
3. 用脚本导出标准 CSV：

```bash
python3 skills/zach-feature-demand-validator/scripts/generate_community_csv.py \
  --data <community.json> \
  --source-ref 'site:reddit.com "air fryer steam"' \
  --output <数据源目录>/05_社区_信号_讨论摘要.csv
```

### Step 4：综合判定

| 判定 | 条件 | 建议 |
|------|------|------|
| ✅ 强真需求 | 三个维度均有正面信号 | 值得投入开发 |
| ⚠️ 弱真需求 | 两个维度有信号，一个维度缺失 | 可考虑，但要承认风险 |
| ❓ 待验证 | 只有一个维度有信号 | 先别上大投入 |
| ❌ 伪需求 | 没有正面信号，或已有明显负面信号 | 不建议投入 |

如果走降级版，综合结论必须把“关键词维度缺失”写进风险提示。

### Step 5：生成报告

交付固定包括：

1. `[日期]_[品类]_[功能]_功能需求验证报告.md`
2. 五个标准 CSV
3. 若走 Review fallback，还要附上：
   - `review_source_pack/source_manifest.json`
   - `review_source_pack/raw/*`

### Step 6：交付校验

```bash
python3 skills/zach-feature-demand-validator/scripts/validate_deliverables.py --dir <output_dir>
```

只有返回 `validate_ok` 才算完成。

---

## 标准输出

```text
工作成果/feature-validation/
├── YYYY-MM-DD_[品类]_[功能]_功能需求验证报告.md
└── YYYY-MM-DD_[品类]_[功能]_数据源/
    ├── 01_review_信号_原始数据.csv
    ├── 02_keyword_信号_搜索量数据.csv
    ├── 03_keyword_信号_趋势数据.csv
    ├── 04_keyword_信号_延伸词.csv
    ├── 05_社区_信号_讨论摘要.csv
    └── review_source_pack/               # 仅 fallback 场景需要
        ├── source_manifest.json
        └── raw/
```

所有 CSV 都必须包含：

- `数据来源`
- `来源类型`
- `来源链接/查询词`
- `原始文件名`
- `采集时间`

---

## Script Directory

| 脚本 | 用途 |
|------|------|
| `scripts/parse_reviews.py` | 解析 Sorftime `product_reviews` JSON |
| `scripts/parse_review_source_pack.py` | 解析手动导出的 Amazon Review 证据包 |
| `scripts/generate_keyword_csv.py` | 关键词数据导出为标准 CSV |
| `scripts/generate_community_csv.py` | 社区讨论导出为标准 CSV |
| `scripts/validate_deliverables.py` | 校验 MD、CSV 和 fallback 证据包是否完整 |
| `scripts/WINDOWS_USAGE.md` | Windows 运行说明 |

---

## 硬性规则

1. ⛔ Sorftime 可用时，Review 和关键词维度优先走 Sorftime
2. ⛔ Sorftime 不可用时，只允许 Review 维度降级，关键词维度必须明确标成未验证
3. ⛔ Review 原始数据必须走 Python 脚本解析，不能把大段原始 JSON / HTML 直接塞进报告
4. ⛔ 每个 CSV 必须保留可核查来源字段
5. ⛔ 负面信号必须写入报告
6. ⛔ 所有结论都要引用具体数据，不允许空泛判断

---

## 参考文档

- `references/csv_schema.md`
- `references/report_template.md`
- `references/judgment_criteria.md`
- `references/keyword_construction_guide.md`
- `references/review_fallback_pack.md`
