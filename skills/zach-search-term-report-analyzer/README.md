# zach-search-term-report-analyzer

> **作者**：Zach ｜ 公众号「Zach的进化笔记」
>
> Learn in public！把 Amazon Ads 搜索词报告变成可复核的否词、控成本、放量和 Listing 反馈清单。

Amazon Ads SP / SB / SD 搜索词报告分析 skill。

v2 把分析拆成三个阶段：

1. 确定性脚本清洗报表、聚合 7/14/30 天指标并聚类词根
2. AI 助手或人工完成词根级语义分类
3. 严格校验分类完整性，通过词根继承生成决策和六类结果

词根继承让低样本长尾词在词根样本足够时获得可解释判断；真正样本不足的碎词进入低量池汇总监控，不再全部堆进“待判定”。

## 推荐安装方式：让 AI 帮你装

推荐在以下 IDE 中直接用自然语言安装：

- Claude Code
- Codex
- Cursor

把下面这句话直接发给你的 AI：

```text
帮我安装 `zach-search-term-report-analyzer` 这个 skill，来源仓库是 `amazon-skills`。直接装到当前工作区，并把依赖一起检查好。
```

手动安装仍然保留，但只作为降级方案：
[../../docs/manual-install.md](../../docs/manual-install.md)

## 快速开始

安装依赖：

```bash
python3 -m pip install -r skills/zach-search-term-report-analyzer/requirements.txt
```

### Stage A：生成工作簿与分类任务

```bash
python3 skills/zach-search-term-report-analyzer/scripts/prepare_search_term_analysis.py \
  skills/zach-search-term-report-analyzer/examples/search-term-report-sample.csv \
  --asin B0PUBLIC01 \
  --brand ExampleBrand \
  --target-acos 0.20 \
  --site US \
  --listing-context-file skills/zach-search-term-report-analyzer/examples/listing-context-sample.md \
  --output-dir outputs/search-term-report-analyzer/ExampleBrand/intermediate/
```

Stage A 会生成：

- `workbook.json`
- `roots_for_review.md`

### Stage B：完成词根分类

让 AI 助手读取以下内容：

- `outputs/search-term-report-analyzer/ExampleBrand/intermediate/roots_for_review.md`
- `references/term_classification.md`
- Listing 上下文

然后把完整分类写入同目录的 `root_classifications.json`。仓库同时提供与公开样例匹配的可复现文件：

```bash
cp skills/zach-search-term-report-analyzer/examples/root-classifications-sample.json \
  outputs/search-term-report-analyzer/ExampleBrand/intermediate/root_classifications.json
```

### Stage C：生成正式结果

```bash
python3 skills/zach-search-term-report-analyzer/scripts/finalize_search_term_report.py \
  outputs/search-term-report-analyzer/ExampleBrand/intermediate/workbook.json \
  --classifications outputs/search-term-report-analyzer/ExampleBrand/intermediate/root_classifications.json \
  --output-dir outputs/search-term-report-analyzer/ExampleBrand/
```

## 输出

正式输出共六类：

- Markdown 主报告
- CSV 搜索词分析明细
- CSV 否词候选清单
- 可筛选、排序、勾选并导出 CSV 的操作台 HTML
- KPI、决策分布和花费去向汇报 HTML
- JSON 运行摘要

两个 HTML 均为自包含单文件，无 CDN、Webfont、外链图片或运行时请求，可直接双击打开。
报告中的数据来源只记录输入文件名，不会写入运行者的本机绝对路径。

## 分类与决策边界

- Stage B 必须覆盖每一个待分类词根，不能使用 `uncertain_term`
- Stage C 遇到缺失分类或非法枚举会明确报错退出
- 单词样本不足但词根样本足够时使用 `basis=root`
- 单词与词根样本都不足时使用 `basis=pool`
- skill 只输出建议，不会自动修改广告预算、bid 或否词
- 实际广告操作前仍需用户确认

## 输入字段

最低需要：

- `date`
- `search_term`
- `clicks`
- `spend`

如果报表包含 impressions、orders、sales 等字段，脚本会重新计算 CTR、CVR、ACOS、CPC 和 ROAS。缺少订单或销售额时，不会伪造转化结论。

## 依赖

- Python 3.10+
- pandas
- beautifulsoup4
- openpyxl
- curl（仅用于可选的 live Listing fetch）

## v1 兼容说明

旧的 `scripts/analyze_search_term_decisions.py` 暂时保留并标记弃用，供已有自动化过渡使用。新任务应使用 Stage A → Stage B → Stage C；旧入口将在后续大版本移除。

## 如果安装或运行出错，直接让 AI 帮你排查

把下面这段直接发给你的 AI，并附上报错信息：

```text
我已经安装了 `zach-search-term-report-analyzer`，但运行时遇到问题。请检查：

1. skill 文件、Python 依赖和脚本路径是否完整
2. 报表字段是否能映射到 date、search_term、clicks、spend
3. Stage A 是否生成 workbook.json 与 roots_for_review.md
4. root_classifications.json 是否覆盖全部待分类词根且枚举合法
5. Stage C 是否生成六类正式输出

如果可以安全修复，请直接修复并重跑最短验证。
```

## 关于作者

关注「**Zach的进化笔记**」，获取 AI x 跨境电商的实战经验、工具和方法论：

<img src="../../assets/traffic/wechat-official-account.jpg" width="200" alt="公众号二维码" />

扫码加入交流群，一起交流 AI + 跨境电商的实战玩法：

<img src="../../assets/traffic/wechat-group.jpeg" width="200" alt="wechat-group" />
