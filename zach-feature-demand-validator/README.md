# zach-feature-demand-validator

> **作者**：Zach ｜ 公众号「Zach的进化笔记」
>
> Learn in public！把亚马逊卖家做“微创新功能判断”的经验，写成 AI 能执行的 SOP。

---

## 这个 Skill 解决什么问题

亚马逊卖家的产品开发，大多数时候不是在发明全新品类，而是在现有市场供给上做一点微创新：

- 加一个小功能
- 补一个小结构
- 修一个小体验

最常见的误判也出在这里。

很多功能看起来很合理，但未必是用户真的在意的需求。卖家觉得合理，不等于市场真的买单。

`zach-feature-demand-validator` 就是拿来做这一步判断的：

**这个功能点，到底是真需求，还是卖家自嗨。**

它会从三个维度交叉验证：

| 维度 | 数据源 | 解决的问题 |
|------|--------|-----------|
| Review 信号 | Sorftime `product_reviews` 或本地 `review_source_pack` | 用户评论里有没有直接提到、抱怨缺失、或对现有实现不满意 |
| 关键词信号 | Sorftime `keyword_detail / trend / extends` | 用户有没有主动搜索这个功能 |
| 社区信号 | WebSearch（Reddit / Quora） | 用户在购买前有没有讨论这个功能 |

---

## 和其他 Skill 的区别

- `zach-product-research`：判断这个市场能不能做
- `zach-feature-demand-validator`：判断这个功能点值不值得做

前者更像“选品”。

后者更像“产品微创新验证”。

---

## 两种运行模式

### 1. Sorftime 完整版

适合已经配置 Sorftime MCP 的用户。

- Review：Sorftime
- 关键词：Sorftime
- 社区：WebSearch

这是完整版。

### 2. 无 Sorftime 降级版

如果你暂时没有 Sorftime MCP，也可以先跑一个降级版：

- Review：本地 `review_source_pack`
- 关键词：明确标记为未验证
- 社区：WebSearch

这不是完整版。

但至少能先把“评论里到底有没有人在乎这个功能”这条证据链跑通，而且所有原始文件都能回查。

---

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/zach22-1999/amazon-skills.git
cd amazon-skills
```

### 2. 复制 Skill 到你的工作目录

```bash
TARGET=~/my-amazon-workspace

mkdir -p "$TARGET/.claude/skills"
cp ./.claude/skills/zach-feature-demand-validator.md "$TARGET/.claude/skills/"
cp -R ./skills/zach-feature-demand-validator "$TARGET/skills/"
```

### 3. 可选：配置 Sorftime MCP

如果你要跑完整版，在你的工作目录创建 `.mcp.json`：

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

### 4. 验证脚本是否可用

```bash
python3 skills/zach-feature-demand-validator/scripts/parse_review_source_pack.py \
  --pack skills/zach-feature-demand-validator/examples/review-source-pack \
  --keywords "steam,steamer,steaming" \
  --output /tmp/feature_validator_review.csv
```

Windows 用户见：

[`skills/zach-feature-demand-validator/scripts/WINDOWS_USAGE.md`](./skills/zach-feature-demand-validator/scripts/WINDOWS_USAGE.md)

---

## 使用方式

### 自然语言

```text
帮我验证一下空气炸锅加蒸汽功能在美国站是不是真需求
帮我验证一下 B0XXXX 的 self-cleaning 功能值不值得做
```

### fallback 证据包

如果没有 Sorftime，你需要提供一个：

```text
review_source_pack/
├── source_manifest.json
└── raw/
```

具体格式见：

[`skills/zach-feature-demand-validator/references/review_fallback_pack.md`](./skills/zach-feature-demand-validator/references/review_fallback_pack.md)

---

## 交付物

- `功能需求验证报告.md`
- 5 个标准 CSV
- fallback 场景额外保留 `review_source_pack`

所有 CSV 都统一带：

- `数据来源`
- `来源类型`
- `来源链接/查询词`
- `原始文件名`
- `采集时间`

这样业务人员可以逐条回查，不用只相信 AI 的结论。

---

## 目录结构

```text
zach-feature-demand-validator/
├── README.md
├── LICENSE
├── .claude/
│   └── skills/
│       └── zach-feature-demand-validator.md
├── examples/
│   └── review-source-pack/
└── skills/
    └── zach-feature-demand-validator/
        ├── SKILL.md
        ├── README.md
        ├── scripts/
        ├── references/
        └── examples/
```

## License

MIT
