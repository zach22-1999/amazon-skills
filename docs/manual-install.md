# Manual Install

当你的 IDE 暂时不能一步完成“自然语言安装”时，再使用这份手动安装说明。

## 1. 克隆仓库

```bash
git clone https://github.com/zach22-1999/amazon-skills.git
cd amazon-skills
```

## 2. 选择目标 skill

当前示例：

- `skills/zach-seller-skill-creator`
- `skills/zach-feature-demand-validator`
- `skills/zach-listing-health-checker`
- `skills/zach-search-term-report-analyzer`

## 3. 放到你的工作区

### Claude Code / Claude App

把目标 skill 目录复制到你的工作区：

```bash
mkdir -p /path/to/your-workspace/.claude/skills
cp -R skills/zach-seller-skill-creator /path/to/your-workspace/.claude/skills/
```

或：

```bash
cp -R skills/zach-feature-demand-validator /path/to/your-workspace/.claude/skills/
cp -R skills/zach-listing-health-checker /path/to/your-workspace/.claude/skills/
cp -R skills/zach-search-term-report-analyzer /path/to/your-workspace/.claude/skills/
```

### Codex / Cursor

优先还是让 AI 读取仓库中的 skill 并帮你完成安装。  
如果你必须手动处理，请把目标 skill 目录复制到你自己的工作区技能目录，或按你当前 IDE 的本地 skill/import 机制指向该目录。

## 4. 验证

安装完成后，对 AI 说：

```text
请使用 zach-seller-skill-creator，帮我把一个亚马逊运营流程做成可复用的 skill。
```
