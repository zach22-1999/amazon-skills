# zach-search-term-analyzer

> **作者**：Zach ｜ 公众号「Zach的进化笔记」
>
> Learn in public！把 Brand Analytics 热门搜索词报告变成"这个词跟我什么关系、该做什么动作"的清单。

Amazon Brand Analytics 热门搜索词报告（Top Search Terms）分析 skill。

核心是一个**场景化框架**：同一份 ABA 数据，你的 ASIN 在不在该词的点击 TOP3 里，要回答的业务问题完全不同——

- **在 TOP3（场景 A，存量经营）**：看自家行的成交系数——A1 收割词（放量防守）/ A2 漏水词（点击拿到转化没接住，先修详情页再抬价）/ A4 份额预警（掉出 TOP3）
- **不在 TOP3（场景 B，市场进入）**：看点击集中度 × 头部满足度——B1 机会词（点击分散且头部接不住需求，转化外流=进入信号）/ B2 常规竞争词 / B3 头部满足词（避其锋芒）/ B4 伏击词（头部霸点击但买家买别家→竞品定向偷单）

三个容易被误读的口径，脚本和报告里都做了防呆：

1. **搜索频率排名 ≠ 搜索量**（相对排名，跨类目不可比）
2. **TOP3 是"点击王"不是"转化王"**（含广告位点击，真正的 closer 可能不在表里）
3. **点击份额与转化份额是独立指标**——TOP3 转化份额为 0 是常见真实现象（转化分散或脱敏），本工具单列"数据不足"不硬判，而不是当成 0 算出错误结论

全部判定阈值（集中度 30/50/70、成交系数 1.0、漏水差 4pt、SFR 五级分层）都是多源实战经验默认值，参数可按类目校准，出处见 `references/关键词分类逻辑说明.md`。

## 推荐安装方式：让 AI 帮你装

推荐在以下 IDE 中直接用自然语言安装：

- Claude Code
- Codex
- Cursor

把下面这句话直接发给你的 AI：

```text
帮我安装 `zach-search-term-analyzer` 这个 skill，来源仓库是 `amazon-skills`。直接装到当前工作区，并把依赖一起检查好。
```

## 手动使用

```bash
# 1. 安装依赖
pip3 install -r skills/zach-search-term-analyzer/scripts/requirements.txt

# 2. 运行分析（推荐提供自家 ASIN，启用场景 A/B 路由）
python3 skills/zach-search-term-analyzer/scripts/analyze_search_terms.py /path/to/reports/ \
  --own-asins "B0XXXXXXXX,B0YYYYYYYY"

# 3. 查看结果：analysis_reports/ 目录（7 组 CSV+MD 报告）
```

不提供 `--own-asins` 时全部按场景 B（市场进入视角）分析——新品上架前本来就是这个场景。

## 输入要求

- Brand Analytics → Top Search Terms（热门搜索词）导出 CSV（UTF-8），支持多期自动合并与去重
- 必需字段：搜索频率排名、搜索词、报告日期、点击量最高的商品 #1/#2/#3（ASIN/点击份额/转化份额）
- 份额字段兼容数值与 `12.34%` 字符串；周报/月报粒度自动识别
- ⚠️ 这不是 PPC 搜索词报告——广告搜索词分析请用 [zach-search-term-report-analyzer](../zach-search-term-report-analyzer/README.md)

## 输出

| 文件 | 内容 |
|---|---|
| `03_搜索词热度分析.csv/.md` ⭐⭐ | 场景化分类核心产物（场景/状态/集中度/满足度/红线/蓝海/自家份额/截流目标） |
| `06_成交系数分析.csv/.md` ⭐ | per-ASIN 成交系数：自家自诊 + 竞品截流目标 + 逆向学习对象 |
| `04_词频统计分析.xlsx/.md` | 单词+双词短语（去重计数，短语只取真实相邻组合） |
| `01/02/05/07` | 品牌上榜频次 / 类别趋势 / 竞争格局 / 时间序列（核心词趋势图） |

## 文档

- `references/关键词分类逻辑说明.md` — 场景框架判定标准 + 阈值依据与来源
- `references/字段说明.md` — 字段口径与陷阱（独立指标/点击王/脱敏/归因窗口）
- `references/分析角度和方法.md` — 7 个维度分别怎么用、不要做什么

## 如果安装或运行出错，直接让 AI 帮你排查

把下面这段直接发给你的 AI，并附上报错信息：

```text
我已经安装了 `zach-search-term-analyzer`，但运行时遇到问题。请检查：

1. skill 文件、Python 依赖（pandas/numpy/matplotlib/seaborn/openpyxl）和脚本路径是否完整
2. CSV 是否为 Brand Analytics 热门搜索词报告（含 搜索频率排名/搜索词/报告日期/点击量最高的商品 #1-#3 份额字段）
3. analysis_reports/ 是否生成 7 组 CSV+MD 报告
4. 如果提供了 --own-asins，03 报告是否出现场景 A 状态

如果可以安全修复，请直接修复并重跑最短验证。
```

## 关于作者

关注「**Zach的进化笔记**」，获取 AI x 跨境电商的实战经验、工具和方法论：

<img src="../../assets/traffic/wechat-official-account.jpg" width="200" alt="公众号二维码" />

扫码加入交流群，一起交流 AI + 跨境电商的实战玩法：

<img src="../../assets/traffic/wechat-group.jpeg" width="200" alt="wechat-group" />
