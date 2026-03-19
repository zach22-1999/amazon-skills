# zach-feature-demand-validator

> **作者**：Zach ｜ 公众号「Zach的进化笔记」
>
> Learn in public！把亚马逊卖家做"微创新功能判断"的经验，写成 AI 能执行的 SOP。

---

## 先搞懂这个 Skill 的定位（30 秒）

| | zach-product-research | zach-feature-demand-validator |
|---|---|---|
| **解决的问题** | 这个市场能不能做 | 这个功能点值不值得做 |
| **分析粒度** | 品类级（市场容量、竞争格局、进入壁垒） | 功能级（一个具体的微创新点） |
| **典型场景** | "美国站蓝牙音箱还有机会吗" | "蓝牙音箱加蒸汽功能是真需求吗" |
| **上下游关系** | 选品的第一步 | 选品之后、开模之前的验证 |

简单说：**product-research 告诉你"做什么品类"，feature-demand-validator 告诉你"做哪个功能点"**。

---

## 这个 Skill 解决什么问题

亚马逊卖家的产品开发，大多数时候不是在发明全新品类，而是在现有产品上做一点微创新：

- 加一个小功能
- 补一个小结构
- 修一个小体验

最常见的误判也出在这里。

很多功能看起来很合理，但未必是用户真的在意的需求。卖家觉得合理，不等于市场真的买单。

`zach-feature-demand-validator` 就是拿来做这一步判断的：

**这个功能点，到底是真需求，还是卖家自嗨。**

---

## 怎么判断的

从三个维度交叉验证，任何单一维度都不足以下结论：

| 维度 | 数据源 | 回答的问题 |
|------|--------|-----------|
| Review 信号 | Sorftime `product_reviews` 或本地 `review_source_pack` | 用户评论里有没有直接提到、抱怨缺失、或对现有实现不满意 |
| 关键词信号 | Sorftime `keyword_detail / trend / extends` | 用户有没有主动搜索这个功能 |
| 社区信号 | WebSearch（Reddit / Quora） | 用户在购买前有没有讨论这个功能 |

三个维度都有信号 → 强需求。只有一个维度有信号 → 需要谨慎。零信号 → 大概率是自嗨。

---

## 前置条件

1. **Claude Code**（或 Cursor / Codex）— 需要支持 MCP 工具调用的 AI 编辑器
2. **Sorftime MCP 账号**（可选）— [sorftime.com](https://sorftime.com/) 跨境电商数据平台
3. **Python 3.9+**

### Sorftime 说明

Sorftime 是完整版的数据源。没有它也能跑降级版（见下方"两种运行模式"）。

- **新用户福利**：首次注册可免费体验 3 天（100 次调用额度）
- **优惠链接**：[点击注册](https://sorftime.com/pc?tag=MjAyNTA3MjQxOTA5MTM5MDA1MzE~)（首月有优惠）
- 注册后在个人中心获取 API Key

### Sorftime MCP 配置

在你的项目根目录或 `~/.claude/` 下的 `.mcp.json` 中添加：

```json
{
  "mcpServers": {
    "sorftime": {
      "type": "sse",
      "url": "https://mcp.sorftime.com/sse?key=YOUR_API_KEY"
    }
  }
}
```

---

## 两种运行模式

### 模式 1：Sorftime 完整版

适合已经配置 Sorftime MCP 的用户。三个维度全部自动化。

| 维度 | 数据来源 |
|------|---------|
| Review | Sorftime `product_reviews` |
| 关键词 | Sorftime `keyword_detail / trend / extends` |
| 社区 | WebSearch（Reddit / Quora） |

### 模式 2：无 Sorftime 降级版

如果你暂时没有 Sorftime MCP，也可以先跑一个降级版：

| 维度 | 数据来源 |
|------|---------|
| Review | 本地 `review_source_pack`（你手动准备的评论数据） |
| 关键词 | 明确标记为"未验证" |
| 社区 | WebSearch（Reddit / Quora） |

不是完整版，但至少能先把"评论里到底有没有人在乎这个功能"这条证据链跑通。所有原始文件都能回查。

---

## 安装步骤

### 第 1 步：克隆仓库

```bash
git clone https://github.com/zach22-1999/amazon-skills.git
cd amazon-skills/zach-feature-demand-validator
```

### 第 2 步：复制 Skill 文件到你的工作目录

```bash
# 把 ~/my-amazon-workspace 替换成你自己的工作目录路径
TARGET=~/my-amazon-workspace

# 复制 Skill 入口文件
mkdir -p "$TARGET/.claude/skills"
cp .claude/skills/zach-feature-demand-validator.md "$TARGET/.claude/skills/"

# 复制完整技能实现
mkdir -p "$TARGET/skills"
cp -R skills/zach-feature-demand-validator "$TARGET/skills/"
```

### 第 3 步：验证安装

```bash
cd $TARGET
python3 skills/zach-feature-demand-validator/scripts/parse_review_source_pack.py \
  --pack skills/zach-feature-demand-validator/examples/review-source-pack \
  --keywords "steam,steamer,steaming" \
  --output /tmp/feature_validator_review.csv
```

看到 CSV 文件生成就说明安装成功。

Windows 用户见：[`skills/zach-feature-demand-validator/scripts/WINDOWS_USAGE.md`](./skills/zach-feature-demand-validator/scripts/WINDOWS_USAGE.md)

---

## 使用方法

### 方式 1：自然语言

```
帮我验证一下空气炸锅加蒸汽功能在美国站是不是真需求
```

```
帮我验证一下 B0XXXX 的 self-cleaning 功能值不值得做
```

### 方式 2：使用降级版（无 Sorftime）

准备一个 `review_source_pack` 目录：

```
review_source_pack/
├── source_manifest.json
└── raw/
    ├── reviews.csv
    └── reviews.txt
```

然后告诉 AI：

```
用这个 review_source_pack 帮我验证 [功能点] 是不是真需求
```

具体格式见：[`references/review_fallback_pack.md`](./skills/zach-feature-demand-validator/references/review_fallback_pack.md)

---

## 交付物

| 文件 | 说明 |
|------|------|
| `功能需求验证报告.md` | 三维度验证结论 + 综合判断 + 建议 |
| 5 个标准 CSV | Review 信号 / 关键词信号 / 社区信号 / 交叉验证 / 综合评分 |
| `review_source_pack`（降级版） | 原始评论数据包，可回查 |

所有 CSV 都统一带溯源字段：`数据来源`、`来源类型`、`来源链接/查询词`、`原始文件名`、`采集时间`。

业务人员可以逐条回查，不用只相信 AI 的结论。

---

## 常见问题

**Q：和 product-research 有什么关系？先跑哪个？**

建议先跑 `product-research` 确定品类可行，再用 `feature-demand-validator` 验证具体功能点。但如果你已经明确要做某个品类，直接跑 validator 也没问题。

**Q：Review 数据从哪来？**

两种方式：① 有 Sorftime 的话自动获取；② 没有的话手动准备 `review_source_pack`（从亚马逊页面复制评论，或导出 CSV）。

**Q：三个维度必须都有信号才算真需求吗？**

不是硬性要求，但交叉验证越多越可靠。单一维度的信号可能是噪音。报告会给出每个维度的置信度，你自己判断。

---

## 项目结构

```
zach-feature-demand-validator/
├── README.md                              # 本文件
├── LICENSE                                # MIT
├── imgs/                                  # 图片资源
├── .claude/
│   └── skills/
│       └── zach-feature-demand-validator.md  # Claude Code 入口文件
├── skills/
│   └── zach-feature-demand-validator/
│       ├── SKILL.md                       # 核心方法论
│       ├── README.md                      # 技能说明
│       ├── scripts/                       # 执行脚本
│       │   ├── parse_reviews.py
│       │   ├── parse_review_source_pack.py
│       │   ├── generate_community_csv.py
│       │   ├── generate_keyword_csv.py
│       │   └── validate_deliverables.py
│       ├── references/                    # 参考文档
│       │   ├── csv_schema.md
│       │   ├── judgment_criteria.md
│       │   ├── keyword_construction_guide.md
│       │   ├── report_template.md
│       │   └── review_fallback_pack.md
│       └── examples/                      # 示例数据
│           └── review-source-pack/
└── examples/
    └── review-source-pack/                # 快速体验用的示例
```

---

## 关于作者

**Zach** — 亚马逊运营多年，正在用 AI 重构跨境电商的工作流。

### 公众号

关注「**Zach的进化笔记**」，获取 AI x 跨境电商的实战经验、工具和方法论：

<img src="./imgs/公众号二维码.jpg" width="200" alt="公众号二维码" />

### 交流群

扫码加入，一起交流 AI + 跨境电商的实战玩法，也欢迎反馈使用中遇到的问题：

<img src="./imgs/群聊二维码.jpeg" width="200" alt="交流群二维码" />

---

## License

MIT License - 详见 [LICENSE](./LICENSE)
