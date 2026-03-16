# zach-product-research

> **作者**：Zach ｜ 公众号「Zach的进化笔记」
>
> Learn in public！亚马逊卖家的 AI 工具箱，用 Skill 把运营经验产品化。

## 这个 Skill 做什么

`zach-product-research` 是一个基于 **Sorftime MCP + Claude Code / Cursor / Codex / OpenClaw** 的亚马逊选品分析工具。

给它一个产品关键词和站点，它会自动调用 Sorftime 数据接口，完成从市场扫描到 Go/No-Go 决策的完整选品分析流程，最终输出一份包含 **四件套交付物** 的市场调研报告。

核心能力：
- 类目市场扫描 + 关键词多维度对比
- Top100 产品属性标注（标题正则 + product_detail 补充验证）
- 多维度交叉分析 → 发现供需缺口和市场空白
- 竞品差评分析（按属性维度归类，而非按产品）
- 进入壁垒评估（6 类壁垒量化）
- Go/No-Go 综合评分（5 维度加权）
- 产品矩阵建议（具体到规格、定价、对标竞品）

## 输出示例

完整示例见 [`examples/bluetooth-speaker/`](./examples/bluetooth-speaker/)（美国站蓝牙音箱），包含：

| 文件 | 说明 |
|------|------|
| `*_市场调研报告_*.md` | 完整 Markdown 报告（10 章结构，约 800 行） |
| `*_精简报告_*.html` | HTML 精简报告（浏览器直接打开，快速浏览关键结论） |
| `*_可视化看板_*.html` | 交互式 Dashboard 看板（图表 + 评分卡 + 热力图） |
| `*_市场调研_数据_*.xlsx` | Excel 多 Sheet 数据（供逐条核对） |
| `unified_payload.json` | 完整 v2 数据包（可重新生成全部交付物） |

## 前置条件

1. **Claude Code**（或 Cursor with Claude）— 需要支持 MCP 工具调用
2. **Sorftime MCP 账号** — [sorftime.com](https://sorftime.com/) 跨境电商数据平台，需购买会员
3. **Sorftime MCP 配置** — 在你的 `.mcp.json` 中配置 sorftime server
4. **Python 3.9+** — 用于 `render_deliverables.py` 脚本
5. **openpyxl** — `pip install openpyxl`

### Sorftime MCP 配置示例

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

> 具体的 API Key 获取方式请参考 [Sorftime 官方文档](https://sorftime.com/)。

## 安装步骤

### 1. 克隆仓库

```bash
git clone https://github.com/YOUR_USERNAME/zach-product-research.git
cd zach-product-research
```

### 2. 复制 Skill 入口文件到你的项目

将 `.claude/skills/zach-product-research.md` 复制到你的 Claude Code 项目的 `.claude/skills/` 目录下：

```bash
# 假设你的工作目录是 ~/my-amazon-workspace
cp -r .claude/skills/zach-product-research.md ~/my-amazon-workspace/.claude/skills/
cp -r skills/zach-product-research ~/my-amazon-workspace/skills/
```

### 3. 配置 Sorftime MCP

确保你的 `.mcp.json` 中已配置 sorftime MCP server（见上方配置示例）。

### 4. 安装 Python 依赖

```bash
pip install openpyxl
```

### 5. 验证安装

```bash
# 用最小样本测试渲染脚本
python skills/zach-product-research/scripts/render_deliverables.py all \
  --input skills/zach-product-research/evals/files/sample_payload_minimal.json \
  --root .
```

如果返回 `validate_ok`，说明安装成功。

## 使用方法

### 方式 1：Skill 命令

```
/zach-product-research bluetooth speaker US
```

### 方式 2：自然语言

```
帮我用 Sorftime 分析一下美国站蓝牙音箱选品机会
```

### 方式 3：带约束条件

```
帮我找美国站月销1000+、价格$15-30、评论门槛低的潜力产品
```

### 参数说明

- **产品关键词**：必填，如 `bluetooth speaker`、`yoga mat`、`dog harness`
- **站点**：可选，默认 `US`，支持 US/GB/DE/FR/IT/ES/CA/JP 等 14 个站点
- **约束条件**：可选，包括价格区间、月销量门槛、预算、品类偏好等

## 工作原理

1. **信息收集** — 确认目标站点、选品场景、约束条件
2. **数据采集** — 调用 Sorftime MCP（category_report / keyword_detail / product_reviews 等 6+ 工具）获取市场数据
3. **结构化分析** — Top100 属性标注 → 交叉分析 → 竞品差评维度归类 → 新品友好度评估
4. **决策输出** — 进入壁垒评估 + Go/No-Go 加权评分 → 产品矩阵建议
5. **一键渲染** — 组装 unified_payload.json → `render_deliverables.py all` → 四件套交付

## 项目结构

```
zach-product-research/
├── README.md                              # 本文件
├── LICENSE                                # MIT
├── .claude/
│   └── skills/
│       └── zach-product-research.md       # Claude Code 入口文件
├── skills/
│   └── zach-product-research/
│       ├── SKILL.md                       # 核心方法论（1100+ 行）
│       ├── scripts/
│       │   ├── render_deliverables.py     # 一键渲染脚本
│       │   ├── parse_top100_dimensions.py # 标题维度解析
│       │   └── cross_analysis.py          # 交叉分析
│       ├── references/
│       │   ├── analysis_patterns.md       # 四种分析模式模板
│       │   ├── payload_schema_v2.md       # v2 数据包结构定义
│       │   └── html_report_spec.md        # HTML 报告规范
│       ├── agents/
│       │   ├── data-pipeline.md           # 数据管道 Agent 定义
│       │   └── insight-writer.md          # 洞察撰写 Agent 定义
│       ├── assets/
│       │   ├── html_report_template.html  # HTML 报告模板
│       │   └── dashboard_template.html    # Dashboard 模板
│       └── evals/
│           ├── evals.json                 # 最小自测套件
│           └── files/
│               └── sample_payload_minimal.json
└── examples/
    └── bluetooth-speaker/
        ├── README.md                      # 示例说明
        ├── unified_payload.json           # 完整 v2 数据包
        ├── *_市场调研报告_*.md             # 完整报告
        ├── *_精简报告_*.html              # HTML 精简报告
        ├── *_可视化看板_*.html            # Dashboard
        └── *_市场调研_数据_*.xlsx         # Excel 数据
```

## 关于作者

**Zach** — 亚马逊运营多年，正在用 AI 重构跨境电商的工作流。

公众号「**Zach的进化笔记**」，分享：
- AI × 跨境电商的实战经验和工具
- Claude Code / Skill 在运营场景中的落地案例
- 从零构建 AI 工作流的方法论
- OpenClaw养虾交流


如果这个工具对你有帮助，欢迎关注公众号交流。

## License

MIT License - 详见 [LICENSE](./LICENSE)
