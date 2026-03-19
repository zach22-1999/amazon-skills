# Amazon Skills

> **作者**：Zach ｜ 公众号「Zach的进化笔记」
>
> Learn in public！亚马逊卖家的 AI 工具箱，用 Skill 把运营经验产品化。

---

## 这个仓库是什么

一套给亚马逊卖家用的 **AI Skill 合集**。

每个 Skill 都是一个完整的方法论 + 执行流程，装进 Claude Code / Cursor 后，AI 就能按你的思路自动跑分析。

不是 prompt 模板，不是聊天记录，是 **可复用、可验证、有交付物的工作流**。

---

## 已发布的 Skills

| Skill | 解决什么问题 | 数据源 | 状态 |
|-------|-------------|--------|------|
| [zach-product-research](./zach-product-research/) | 给一个关键词，自动完成选品分析，输出 Go/No-Go 决策 + 四件套报告 | Sorftime MCP | ✅ 已发布 |
| [zach-feature-demand-validator](./zach-feature-demand-validator/) | 验证一个功能点是真需求还是卖家自嗨，三维度交叉验证 | Sorftime MCP + WebSearch | ✅ 已发布 |

每个 Skill 目录下都有独立的 README，包含安装步骤、使用说明和示例输出。

---

## 什么是 Skill

Skill 是 Claude Code 的能力扩展文件（`.md`），定义了一套可复用的工作流程。

你可以把它理解为：**把运营经验写成 AI 能执行的 SOP**。

每个 Skill 包含：
- **方法论** — 分析框架、决策标准、硬性规则
- **执行步骤** — 数据采集 → 分析 → 交付，每一步可验证
- **渲染脚本** — 自动生成报告 / Excel / Dashboard
- **示例输出** — 装上就能看到效果

---

## 前置条件

- [Claude Code](https://claude.ai/claude-code)（或 Cursor / Codex 等支持 MCP 的工具）
- [Sorftime MCP](https://sorftime.com/) 账号 + API Key
- Python 3.9+ & `pip install openpyxl`

### Sorftime 说明

Sorftime 是这些 Skill 的核心数据源，没有它就没有数据可分析。

- **新用户福利**：首次注册可免费体验 3 天（100 次调用额度），足够跑几个品类试试效果
- **优惠链接**：[点击注册](https://sorftime.com/pc?tag=MjAyNTA3MjQxOTA5MTM5MDA1MzE~)（首月有优惠）
- 注册后在个人中心获取 API Key

---

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/zach22-1999/amazon-skills.git
cd amazon-skills

# 2. 选一个 Skill，按其 README 安装
cd zach-product-research
cat README.md
```

每个 Skill 目录下都有独立的 README，包含完整的安装步骤和使用说明。

---

## 项目结构

```
amazon-skills/
├── README.md                          # 本文件
├── zach-product-research/             # 选品分析 Skill
│   ├── README.md                      # 安装和使用说明
│   ├── .claude/skills/                # Claude Code 入口文件
│   ├── skills/zach-product-research/  # 方法论 + 脚本 + 模板
│   └── examples/bluetooth-speaker/    # 蓝牙音箱完整示例
└── zach-feature-demand-validator/     # 功能需求验证 Skill
    ├── README.md                      # 安装和使用说明
    ├── .claude/skills/                # Claude Code 入口文件
    ├── skills/zach-feature-demand-validator/  # 方法论 + 脚本
    └── examples/review-source-pack/   # 评论数据示例
```

---

## 关于作者

**Zach** — 亚马逊运营多年，正在用 AI 重构跨境电商的工作流。

### 公众号

关注「**Zach的进化笔记**」，获取 AI x 跨境电商的实战经验、工具和方法论：

<img src="./zach-product-research/imgs/公众号二维码.jpg" width="200" alt="公众号二维码" />

### 交流群

扫码加入，一起交流 AI + 跨境电商的实战玩法：

<img src="./zach-product-research/imgs/群聊二维码.jpeg" width="200" alt="交流群二维码" />

---

## License

MIT
