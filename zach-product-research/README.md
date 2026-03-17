# zach-product-research

> **作者**：Zach ｜ 公众号「Zach的进化笔记」
>
> Learn in public！亚马逊卖家的 AI 工具箱，用 Skill 把运营经验产品化。

---

## 先搞懂两个概念（30 秒）

| 概念 | 一句话解释 |
|------|-----------|
| **Skill** | 写给 AI 的 SOP——你把选品方法论写成结构化文档，AI 就能按照你的流程一步步执行，不再需要你反复口头教它。 |
| **MCP** | AI 调用外部数据的接口——让 Claude 能直接查 Sorftime 的市场数据，而不是靠你手动截图粘贴。 |

不需要深入理解原理，知道这两个东西配合起来能让 AI 自动帮你跑选品分析就够了。

---

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

1. **Claude Code**（或 Cursor with Claude）— 需要支持 MCP 工具调用的 AI 编辑器
2. **Sorftime MCP 账号** — [sorftime.com](https://sorftime.com/) 跨境电商数据平台，需购买会员
3. **Python 3.9+** — 用于 `render_deliverables.py` 渲染脚本
4. **openpyxl** — `pip install openpyxl`

### Sorftime 说明

Sorftime 是这个 Skill 的数据源，没有它就没有数据可分析。

- **新用户福利**：首次注册可免费体验 3 天（100 次调用额度），足够跑几个品类试试效果
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

把 `YOUR_API_KEY` 替换为你在 Sorftime 后台获取的 API Key。

---

## 安装步骤

### 第 1 步：克隆仓库

把这个项目下载到本地。

```bash
git clone https://github.com/zach22-1999/amazon-skills.git
cd amazon-skills
```

### 第 2 步：复制 Skill 文件到你的工作目录

Claude Code 通过 `.claude/skills/` 目录识别可用技能，所以需要把 Skill 文件放到你自己的工作目录下。

```bash
# 把 ~/my-amazon-workspace 替换成你自己的工作目录路径
TARGET=~/my-amazon-workspace

# 复制 Skill 入口文件（Claude Code 靠这个文件发现技能）
mkdir -p $TARGET/.claude/skills
cp .claude/zach-product-research.md $TARGET/.claude/skills/

# 复制完整技能实现（方法论 + 脚本 + 模板）
cp -r skills/zach-product-research $TARGET/skills/
```

### 第 3 步：配置 Sorftime MCP

让 Claude 能访问 Sorftime 数据。在你的工作目录下创建或编辑 `.mcp.json`（见上方配置示例）。

### 第 4 步：安装 Python 依赖

渲染脚本需要 openpyxl 来生成 Excel 文件。

```bash
pip install openpyxl
```

### 第 5 步：验证安装

跑一下最小样本，确认脚本能正常工作。

```bash
cd $TARGET
python skills/zach-product-research/scripts/render_deliverables.py all \
  --input skills/zach-product-research/evals/files/sample_payload_minimal.json \
  --root .
```

看到 `validate_ok` 就说明安装成功。

---

## 常见问题

**Q：在 Claude Code 里输入 `/zach-product-research` 没反应？**

检查 `.claude/skills/zach-product-research.md` 文件是否在你的工作目录下。Claude Code 只会加载当前工作目录的 `.claude/skills/` 里的技能。另外确认文件名没有多余的空格或后缀。

**Q：MCP 连不上 Sorftime？**

1. 确认 `.mcp.json` 放在了项目根目录（和 `.claude/` 同级）或 `~/.claude/` 下
2. 确认 API Key 正确，没有多余的空格或换行
3. 在 Claude Code 里输入 `你能看到 sorftime 的工具吗？`，看它是否能列出 sorftime 相关工具
4. 若仍不行，重启 Claude Code 让它重新加载 MCP 配置

**Q：render 脚本报错？**

- `ModuleNotFoundError: No module named 'openpyxl'` → 执行 `pip install openpyxl`
- `FileNotFoundError` → 检查 `--input` 和 `--root` 路径是否正确，确认 `skills/zach-product-research/` 目录结构完整
- Python 版本过低 → 需要 3.9+，用 `python --version` 检查

**Q：我用的是 Cursor，能用吗？**

可以。Cursor 支持 MCP，配置方式和 Claude Code 相同。在 Cursor 设置中添加 MCP server，然后在对话中引用 Skill 内容即可。

---

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

---

## 没有 Claude Code？在 Coze 上也能用（降级版）

如果你还没有 Claude Code 或 Cursor，可以在 [Coze（扣子）](https://www.coze.cn) 上搭一个降级版来体验核心分析逻辑。

### 限制说明

| | Claude Code 完整版 | Coze 降级版 |
|---|---|---|
| 数据获取 | 自动调用 Sorftime MCP | 需要你手动从 Sorftime 网页版复制 Top100 数据 |
| 分析深度 | 全流程自动化（10 章报告） | 基于你粘贴的数据做分析，深度取决于数据量 |
| 交付物 | 四件套（MD + HTML + Dashboard + Excel） | 仅文本分析结果 |
| 适合谁 | 需要完整选品报告的卖家 | 先体验分析逻辑，后续再升级工具 |

### 配置步骤

1. 打开 [coze.cn](https://www.coze.cn)，新建 **Bot**
2. **名称**：例如「亚马逊选品分析器」
3. **人设 / 系统指令**：
   - 打开本仓库的 `skills/zach-product-research/SKILL.md`
   - 复制"核心方法论"部分（分析框架、评估维度、评分标准）到 Coze 的系统提示词
   - 不需要复制脚本调用和 MCP 相关的步骤
4. **开场白**（可选）：「请告诉我你要分析的产品类目和站点，并粘贴 Sorftime Top100 数据，我会按选品方法论进行分析。」
5. 保存并发布

**使用方式**：去 Sorftime 网页版查出 Top100 数据 → 复制粘贴给 Bot → Bot 按方法论分析并输出结论。

> 完整体验（自动数据采集 + 四件套交付）推荐使用 Claude Code 或 Cursor。

---

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
├── imgs/                                  # 图片资源
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
