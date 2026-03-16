# 示例：美国站蓝牙音箱（Bluetooth Speaker）市场调研

## 品类信息

- **站点**：美国站（US）
- **品类**：Bluetooth Speaker / Portable Speaker
- **数据日期**：2026-03-16
- **数据来源**：Sorftime MCP（7 个工具调用）

## 包含的文件

| 文件 | 说明 |
|------|------|
| `unified_payload.json` | 完整 v2 数据包（可直接用 `render_deliverables.py` 重新生成交付物） |
| `20260316_US_bluetooth-speaker_市场调研报告_v1_20260316.md` | Markdown 完整报告（10 章结构） |
| `20260316_US_bluetooth-speaker_精简报告_v1_20260316.html` | HTML 精简报告（浏览器直接打开） |
| `20260316_US_bluetooth-speaker_可视化看板_v1_20260316.html` | 交互式 Dashboard 看板 |
| `20260316_US_bluetooth-speaker_市场调研_数据_v1_20260316.xlsx` | Excel 多 Sheet 数据工作簿 |

## 如何用 unified_payload.json 重新生成

如果你想验证 `render_deliverables.py` 的完整流程，可以用以下命令从 `unified_payload.json` 重新生成全部交付物：

```bash
cd <项目根目录>

python skills/zach-product-research/scripts/render_deliverables.py all \
  --input examples/bluetooth-speaker/unified_payload.json \
  --root .
```

这会在当前目录下按标准路径生成 MD / HTML / Dashboard / Excel 四件套。

## 文件命名规范

文件名格式：`[YYYYMMDD]_[站点]_[品类slug]_[报告类型]_[版本].扩展名`

- `YYYYMMDD`：数据采集日期
- 站点：US / GB / DE 等
- 品类 slug：小写+连字符
- 版本：`v{N}_{YYYYMMDD}`

## 注意事项

- 本示例数据来自 Sorftime MCP 真实调用，数据时效约 30 天
- `unified_payload.json` 包含完整的 Top100 产品数据、属性标注、交叉分析、竞品差评等
- Excel 中的数据可逐条追溯到 Sorftime MCP 的具体工具调用
