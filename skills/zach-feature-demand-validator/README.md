# zach-feature-demand-validator

功能需求真伪验证器。

这个 Skill 不解决“我要不要做这个品类”，而是解决另一个更常见的问题：

**这个微创新功能，到底是不是用户真的在意。**

对亚马逊卖家来说，大多数产品开发都不是颠覆式创新，而是在现有市场供给上做微创新。问题也往往出在这里：功能看起来合理，不代表需求真实存在。

这个 Skill 用三维数据交叉验证：

| 维度 | 数据源 | 作用 |
|------|--------|------|
| Review 信号 | Sorftime `product_reviews` 或本地 `review_source_pack` | 看用户评论里有没有直接提到、抱怨缺失、或者对现有实现不满意 |
| 关键词信号 | Sorftime `keyword_detail` / `keyword_trend` / `keyword_extends` | 看用户有没有主动搜索这个功能 |
| 社区信号 | WebSearch（Reddit + Quora） | 看用户在购买前有没有讨论这个功能 |

## 两种使用模式

### 1. Sorftime 完整版

适合已经配置 Sorftime MCP 的环境。

- Review 维度：Sorftime
- 关键词维度：Sorftime
- 社区维度：WebSearch

### 2. 无 Sorftime 降级版

适合暂时没有 Sorftime MCP，但手里已经有 Amazon 评论证据的人。

- Review 维度：`review_source_pack`
- 关键词维度：明确写“未验证 / 待补充”
- 社区维度：WebSearch

这不是完整版，但至少能把“评论里到底有没有人在乎这个功能”这条证据链先跑通。

## 快速使用

### 业务输入

```text
帮我验证一下 air fryer 加 steam 功能在美国站是不是真需求
帮我验证一下 B0XXXX 的 self-cleaning 功能在 US 站值不值得做
```

### Review fallback 输入

```text
review_source_pack/
├── source_manifest.json
└── raw/
    ├── reviews.csv
    ├── reviews.txt
    └── reviews.html
```

详细格式见 [`references/review_fallback_pack.md`](./references/review_fallback_pack.md)。

## 核心脚本

| 脚本 | 用途 |
|------|------|
| `scripts/parse_reviews.py` | 解析 Sorftime Review JSON |
| `scripts/parse_review_source_pack.py` | 解析本地 Review 证据包 |
| `scripts/generate_keyword_csv.py` | 生成关键词标准 CSV |
| `scripts/generate_community_csv.py` | 生成社区标准 CSV |
| `scripts/validate_deliverables.py` | 校验 MD + CSV + fallback 证据包 |

Windows 用户见 [`scripts/WINDOWS_USAGE.md`](./scripts/WINDOWS_USAGE.md)。

## 交付物

- 一份 Markdown 验证报告
- 五个标准 CSV
- 若走 fallback，再附一份可核查的 `review_source_pack`

所有 CSV 都会统一输出以下核查字段：

- `数据来源`
- `来源类型`
- `来源链接/查询词`
- `原始文件名`
- `采集时间`

## 上下游

- **上游**：`zach-product-research`、`zach-competitor-deep-dive`
- **下游**：`zach-new-product-listing-writer`
