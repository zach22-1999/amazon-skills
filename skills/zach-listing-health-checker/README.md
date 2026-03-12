# zach-listing-health-checker

以真实消费者视角检查亚马逊 Listing 健康状态。

## 快速开始

```
/zach-listing-health-checker B0CR1R7FKP US Ikarao "wireless microphone, karaoke microphone"
```

## 是什么

一个纯网页抓取的 Listing 健康检查工具。不使用任何 API 或第三方数据工具，100% 模拟消费者打开亚马逊页面时能看到的内容。

## 检查哪些内容

| # | 检查项 | 说明 |
|---|--------|------|
| 1 | 页面可访问性 | 非狗狗页面/404 |
| 2 | 价格与优惠 | 售价、折扣、优惠券 |
| 3 | 卖家信息 | Sold By 校验、Buy Box |
| 4 | 购物车状态 | Add to Cart 按钮 |
| 5 | 配送信息 | 配送时间、Prime |
| 6 | 类目与节点 | 大类 + 面包屑路径 |
| 7 | BSR 排名 | 各层级排名 |
| 8 | 差评监控 | 首页差评数量与内容 |
| 9 | 搜索可见性 | 关键词搜索结果中是否找到 |

## 使用场景

- **新品上架验收**：上架 24-48 小时后检查一切是否正常
- **日常巡检**：每周例行检查核心 ASIN
- **异常排查**：销量下降时排查链接问题

## 输出

Markdown 格式的健康检查报告，保存至：
```
工作成果/brands/{品牌名}/listing-health-check/{日期}_{ASIN}_健康检查报告.md
```

## 支持站点

US / UK / DE / FR / IT / ES / CA / JP / MX / AU

## 依赖

- Python 3 + beautifulsoup4（`pip install beautifulsoup4`）
- curl（系统自带）
- 脚本位于 `scripts/` 目录：`browser_utils.py`（通用抓取模块）、`fetch_amazon_page.py`（商品页）、`fetch_amazon_search.py`（搜索页）

## 详细文档

完整方法论见 [SKILL.md](./SKILL.md)
