# amazon-skills

> **作者**：Zach ｜ 公众号「Zach的进化笔记」
>
> Learn in public！亚马逊卖家的 AI 工具箱，用 Skill 把运营经验产品化。

## Skills

| Skill | 说明 | 状态 |
|-------|------|------|
| [zach-product-research](./zach-product-research/) | 基于 Sorftime MCP 的选品分析，从市场扫描到 Go/No-Go 决策 | ✅ 已发布 |

## 什么是 Skill

Skill 是 Claude Code 的能力扩展文件（`.md`），定义了一套可复用的工作流程。

你可以把它理解为：**把运营经验写成 AI 能执行的 SOP**。

每个 Skill 包含：
- 方法论（分析框架、决策标准、硬性规则）
- 执行步骤（数据采集 → 分析 → 交付）
- 渲染脚本（自动生成报告 / Excel / Dashboard）
- 示例输出（装上就能看到效果）

## 前置条件

- [Claude Code](https://claude.ai/claude-code)（或 Cursor / Codex 等支持 MCP 的工具）
- [Sorftime MCP](https://sorftime.com/) 账号 + API Key
- Python 3.9+ & `pip install openpyxl`

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/zach22-1999/amazon-skills.git
cd amazon-skills

# 2. 选一个 Skill，按其 README 安装
cd zach-product-research
cat README.md
```

每个 Skill 目录下都有独立的 README，包含安装步骤和使用说明。

## 关于作者

**Zach** — 亚马逊运营多年，正在用 AI 重构跨境电商的工作流。

公众号「**Zach的进化笔记**」，分享：
- AI × 跨境电商的实战经验和工具
- Claude Code / Skill 在运营场景中的落地案例
- 从零构建 AI 工作流的方法论
- OpenClaw养虾交流

如果这些工具对你有帮助，欢迎关注公众号交流。

## License

MIT
