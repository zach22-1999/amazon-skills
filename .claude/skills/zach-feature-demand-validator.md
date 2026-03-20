---
name: zach-feature-demand-validator
description: 功能需求真伪验证器。面向亚马逊产品开发中的微创新判断，用 Review 信号、关键词信号、社区信号三维度交叉验证某个功能点是真需求还是伪需求。优先调用 Sorftime MCP；无 Sorftime 时自动切换到 WebSearch + WebFetch + Google Trends 替代方案，三个维度都有真实数据采集。
argument-hint: "[品类/ASIN] [功能描述] [站点]"
user-invocable: true
allowed-tools: Read, Glob, Bash, Write, WebSearch, WebFetch
---

# 功能需求真伪验证器

这个 Skill 解决的不是“要不要做这个品类”，而是更常见的微创新判断：

**在现有市场供给上加一个小功能，这件事到底值不值得做。**

## 使用方式

### 方式 1：品类 + 功能
```text
/zach-feature-demand-validator air fryer steam US
```

### 方式 2：ASIN + 功能
```text
/zach-feature-demand-validator B0XXXX self-cleaning US
```

### 方式 3：自然语言
```text
帮我验证一下空气炸锅加蒸汽功能在美国站是不是真需求
```

## 执行顺序

1. 读取 `skills/zach-feature-demand-validator/SKILL.md`
2. 解析输入并构造 3-5 个关键词变体
3. 优先检测是否可用 Sorftime MCP
4. Review 维度：
   - 有 Sorftime：走 `product_reviews` + `scripts/parse_reviews.py`
   - 无 Sorftime：走 `review_source_pack` + `scripts/parse_review_source_pack.py`
5. 关键词维度：
   - 有 Sorftime：走 `keyword_detail / keyword_trend / keyword_extends`
   - 无 Sorftime：明确写“未验证 / 待补充”，不伪造
6. 社区维度：WebSearch 搜 Reddit / Quora，并用脚本导出 CSV
7. 生成报告并运行 `scripts/validate_deliverables.py`

## 输出

- `[日期]_[品类]_[功能]_功能需求验证报告.md`
- `01_review_信号_原始数据.csv`
- `02_keyword_信号_搜索量数据.csv`
- `03_keyword_信号_趋势数据.csv`
- `04_keyword_信号_延伸词.csv`
- `05_社区_信号_讨论摘要.csv`
- fallback 场景额外保留 `review_source_pack/`

## 强制要求

- Sorftime 可用时必须优先调用
- 无 Sorftime 时只允许 Review 维度降级
- **ASIN 必须是真实 10 位编号**（如 B0CR1R7FKP），脚本会强制校验，MULTI/UNKNOWN/占位符会报错退出
- **多 ASIN 场景必须按 ASIN 分组**：每个 ASIN 单独调用 `parse_reviews.py --asin`，或 JSON 中每条 review 自带 ASIN 字段
- 每个 CSV 都必须带可核查来源字段
- 负面证据必须写进报告
- 只有 `validate_ok` 才算完成
