#!/usr/bin/env python3
"""Stage C — 搜索词报告决策与渲染（架构契约 §5/§6 实现）。

读取 Stage A 的 workbook.json 与 Stage B 的 root_classifications.json，
执行有序决策规则（词根继承 + 低量池治理），产出六件输出：
主报告 md / 明细 csv / 否词清单 csv / 操作台 html / 汇报 html / run_summary.json。

用法：
  python3 finalize_search_term_report.py <workbook.json> \
      --classifications <root_classifications.json> --output-dir <dir> \
      [--report-title-prefix "YYYY-MM-DD_品牌_ASIN"] \
      [--console-template <path>] [--report-template <path>]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DEFAULT_CONSOLE_TEMPLATE = SKILL_ROOT / "assets" / "console_template.html"
DEFAULT_REPORT_TEMPLATE = SKILL_ROOT / "assets" / "report_template.html"
PAYLOAD_PLACEHOLDER = "__PAYLOAD_JSON__"

# ---------------------------------------------------------------------------
# 阈值（契约 §5，集中常量，禁散写）
# ---------------------------------------------------------------------------
THRESHOLDS = {
    "min_clicks_for_judgement": 8,        # term 级样本门槛
    "root_min_clicks_for_judgement": 12,  # root 级样本门槛
    "min_clicks_for_priority": 15,
    "min_clicks_for_scale_up": 12,
    "min_spend_for_attention": 10.0,
    "high_spend_without_orders": 15.0,
    "near_avg_cvr_band": 0.15,
    "high_cvr_band": 0.20,
    "low_cvr_band": 0.20,
    "trend_change_band": 0.20,
    "max_target_acos_multiple_for_scale_up": 1.15,
    "very_high_target_acos_multiple": 1.50,
    "negative_min_clicks": 2,             # 无关词进否词的最低点击
    "negative_min_spend": 1.0,            # 或最低花费
}

VALID_CATEGORIES = {
    "brand_term",
    "competitor_term",
    "core_category_term",
    "attribute_term",
    "scenario_term",
    "irrelevant_term",
    "asin_term",
}
VALID_RELEVANCE = {"high", "medium", "low"}
ATTR_SCENARIO_CATEGORIES = {"attribute_term", "scenario_term"}
DECISION_KEYS = [
    "scale_up",
    "hold_test",
    "reduce_bid",
    "negative_candidate",
    "listing_feedback",
    "observe",
    "manual_review",
]

# 覆盖度判断用的简易停用词（与契约 §3 Stage A 停用词表同源子集）
COVERAGE_STOP_WORDS = {
    "for", "with", "the", "a", "an", "of", "to", "in", "on",
    "and", "or", "my", "your", "best", "new",
}

# w7 点击上升判定：w7 日均点击 ≥ w30 日均点击 ×(1+trend_change_band)，
# 且 w7 点击 >= 2（防单点噪声）。w30 的日均按报表实际覆盖天数折算，
# 报表跨度 ≤7 天时 w7≈w30 无趋势判断依据，恒不判上升（数据诚信：不造趋势）。
# 契约只写"w7 点击上升"，此为确定性实现。
W7_RISING_MIN_CLICKS = 2


class ClassificationValidationError(ValueError):
    """classifications 校验失败（覆盖率 / 枚举），fail loud。"""

    def __init__(self, problems: list):
        self.problems = list(problems)
        super().__init__("classifications 校验失败：\n" + "\n".join(f"  - {p}" for p in self.problems))


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError as exc:
            # 指明是哪个文件损坏（workbook / classifications），方便排障
            raise ValueError(f"{path} JSON 解析失败：{exc}") from exc


def safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def num(value: Any, default: float = 0.0) -> float:
    """安全取数：None → default。"""
    if value is None:
        return default
    return float(value)


def fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def fmt_money(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def tokenize_simple(text: str) -> list:
    out = []
    word = []
    for ch in text.lower():
        if ch.isalnum():
            word.append(ch)
        else:
            if word:
                out.append("".join(word))
                word = []
    if word:
        out.append("".join(word))
    return out


# ---------------------------------------------------------------------------
# 启动严格校验（契约 §5：覆盖率 + 枚举，fail loud exit 1）
# ---------------------------------------------------------------------------

def validate_classifications(workbook: dict, classifications: dict) -> None:
    problems = []
    cls_roots = classifications.get("roots")
    if not isinstance(cls_roots, dict):
        raise ClassificationValidationError(["classifications 缺少 roots 对象"])

    required = list((workbook.get("classification_request") or {}).get("roots_to_classify") or [])
    for root_id in required:
        if root_id not in cls_roots:
            problems.append(f"缺少词根分类：{root_id}")

    for root_id, entry in cls_roots.items():
        if not isinstance(entry, dict):
            problems.append(f"词根 {root_id} 的分类条目不是对象")
            continue
        category = entry.get("category")
        if category not in VALID_CATEGORIES:
            problems.append(f"词根 {root_id} category 非法：{category!r}（合法值：{sorted(VALID_CATEGORIES)}）")
        relevance = entry.get("relevance")
        if relevance not in VALID_RELEVANCE:
            problems.append(f"词根 {root_id} relevance 非法：{relevance!r}（合法值：high/medium/low）")

    overrides = classifications.get("term_overrides") or {}
    if not isinstance(overrides, dict):
        problems.append("term_overrides 必须是对象")
        overrides = {}
    for term, entry in overrides.items():
        if not isinstance(entry, dict):
            problems.append(f"term_override {term} 不是对象")
            continue
        category = entry.get("category")
        if category not in VALID_CATEGORIES:
            problems.append(f"term_override {term} category 非法：{category!r}")
        relevance = entry.get("relevance")
        if relevance not in VALID_RELEVANCE:
            problems.append(f"term_override {term} relevance 非法：{relevance!r}")

    # 每个 term 的分类必须可解析：hard_tag / override / 已分类词根 / 词根 hard_tag
    roots_index = {r.get("root_id"): r for r in workbook.get("roots") or []}
    for term in workbook.get("terms") or []:
        term_text = term.get("search_term")
        if term.get("hard_tag"):
            continue
        if term_text in overrides:
            continue
        root_id = term.get("root_id")
        root = roots_index.get(root_id)
        if root is None:
            problems.append(f"词 {term_text} 的词根 {root_id} 不在 workbook.roots 中")
            continue
        if root_id in cls_roots:
            continue
        if root.get("hard_tag"):
            continue
        problems.append(f"词 {term_text} 无法解析类别：词根 {root_id} 未分类且无硬标签")

    if problems:
        raise ClassificationValidationError(problems)


# ---------------------------------------------------------------------------
# effective_category / sample_basis（契约 §5）
# ---------------------------------------------------------------------------

def effective_classification(term: dict, root: Optional[dict], classifications: dict) -> dict:
    """hard_tag ➜ term_override ➜ root.category；brand/asin 视为 relevance=high。"""
    hard_tag = term.get("hard_tag")
    if hard_tag:
        return {
            "category": hard_tag,
            "relevance": "high",
            "needs_listing_check": False,
            "source": "hard_tag",
            "note": "",
        }
    overrides = classifications.get("term_overrides") or {}
    override = overrides.get(term.get("search_term"))
    if override:
        return {
            "category": override["category"],
            "relevance": override["relevance"],
            "needs_listing_check": bool(override.get("needs_listing_check", False)),
            "source": "term_override",
            "note": override.get("note") or "",
        }
    root_id = term.get("root_id")
    cls_roots = classifications.get("roots") or {}
    entry = cls_roots.get(root_id)
    if entry:
        return {
            "category": entry["category"],
            "relevance": entry["relevance"],
            "needs_listing_check": bool(entry.get("needs_listing_check", False)),
            "source": "root",
            "note": entry.get("note") or "",
        }
    if root is not None and root.get("hard_tag"):
        return {
            "category": root["hard_tag"],
            "relevance": "high",
            "needs_listing_check": False,
            "source": "root_hard_tag",
            "note": "",
        }
    # 启动校验已保证不可达；防御性兜底
    raise ValueError(f"词 {term.get('search_term')} 无法解析类别（词根 {root_id}）")


def sample_basis(term: dict, root: Optional[dict]) -> tuple:
    """返回 (basis, m)：term ≥8 点击用 term.total；否则 root ≥12 点击用 root.total；否则 pool。"""
    term_total = (term.get("metrics") or {}).get("total") or {}
    if num(term_total.get("clicks")) >= THRESHOLDS["min_clicks_for_judgement"]:
        return "term", term_total
    root_total = ((root or {}).get("metrics") or {}).get("total") or {}
    if num(root_total.get("clicks")) >= THRESHOLDS["root_min_clicks_for_judgement"]:
        return "root", root_total
    return "pool", term_total


def compute_confidence(basis: str, term_clicks: float, root_clicks: float) -> str:
    if basis == "term" and term_clicks >= 15:
        return "high"
    if basis == "term" or root_clicks >= 20:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Listing 覆盖判断（确定性）
# ---------------------------------------------------------------------------

def listing_covered(term_text: str, listing_context: Optional[str]) -> Optional[bool]:
    """None = 无 Listing 上下文（无法判断，不触发 listing_feedback，数据诚信）。

    覆盖判定：词的所有非停用词 token 均以子串形式出现在 Listing 文本中 → 覆盖。
    """
    if not listing_context:
        return None
    listing_lower = str(listing_context).lower()
    tokens = [t for t in tokenize_simple(term_text) if t not in COVERAGE_STOP_WORDS and not t.isdigit()]
    if not tokens:
        return True
    for token in tokens:
        if token not in listing_lower:
            return False
    return True


def report_span_days(meta: dict) -> Optional[int]:
    """报表实际覆盖天数（date_range 含首尾）；解析失败返回 None。"""
    date_range = meta.get("date_range") or []
    if len(date_range) < 2:
        return None
    try:
        start = datetime.strptime(str(date_range[0]), "%Y-%m-%d")
        end = datetime.strptime(str(date_range[1]), "%Y-%m-%d")
    except ValueError:
        return None
    days = (end - start).days + 1
    return days if days > 0 else None


def w7_clicks_rising(term: dict, span_days: Optional[int]) -> bool:
    """w7 日均点击 ≥ w30 日均点击 ×(1+band) 判上升。

    w30 的日均按报表实际覆盖天数折算（far_days = min(30, span_days)）：
    否则周报（跨度 ≤7 天）里 w7==w30，旧式 ×30/7 外推会把所有 ≥2 点击的词
    误判为上升。跨度 ≤7 天或未知时无趋势判断依据，返回 False。
    """
    metrics = term.get("metrics") or {}
    w7 = metrics.get("w7") or {}
    w30 = metrics.get("w30") or {}
    w7_clicks = num(w7.get("clicks"))
    w30_clicks = num(w30.get("clicks"))
    if w7_clicks < W7_RISING_MIN_CLICKS:
        return False
    if span_days is None or span_days <= 7:
        return False
    far_days = float(min(30, span_days))
    if w30_clicks <= 0:
        return True
    return (w7_clicks / 7.0) >= (w30_clicks / far_days) * (1.0 + THRESHOLDS["trend_change_band"])


# ---------------------------------------------------------------------------
# 决策算法（契约 §5，有序规则，禁止兜底 observe）
# ---------------------------------------------------------------------------

def decide_term(term: dict, root: Optional[dict], cls: dict, meta: dict) -> dict:
    t = THRESHOLDS
    term_total = (term.get("metrics") or {}).get("total") or {}
    term_clicks = num(term_total.get("clicks"))
    term_spend = num(term_total.get("spend"))
    term_orders = num(term_total.get("orders"))
    root_total = ((root or {}).get("metrics") or {}).get("total") or {}
    root_clicks = num(root_total.get("clicks"))

    basis, m = sample_basis(term, root)
    confidence = compute_confidence(basis, term_clicks, root_clicks)

    category = cls["category"]
    relevance = cls["relevance"]
    baseline = meta.get("baseline") or {}
    baseline_cvr = baseline.get("cvr")
    target_acos = meta.get("target_acos")
    has_orders_data = bool(meta.get("has_orders_data", True))
    listing_context = meta.get("listing_context")

    m_clicks = num(m.get("clicks"))
    m_spend = num(m.get("spend"))
    m_orders = num(m.get("orders"))
    m_cvr = m.get("cvr")
    m_acos = m.get("acos")

    decision = None
    reason = ""
    bucket = None
    neg_suggestion = None

    # 1. ASIN 串号词
    if category == "asin_term":
        decision, reason = "manual_review", "ASIN 串号词，人工判断承接来源"

    # 2. 分类层标记需查 Listing
    elif cls.get("needs_listing_check"):
        decision, reason = "manual_review", "分类时标记 needs_listing_check，需人工结合 Listing 复核"

    # 3. 品牌词
    elif category == "brand_term":
        bucket = "brand"
        if term_orders <= 0 and term_spend >= t["high_spend_without_orders"]:
            decision, reason = "manual_review", "品牌词高耗0单，查承接页"
        else:
            decision, reason = "hold_test", "品牌承接/防守，保持"

    # 4. 竞品词
    elif category == "competitor_term":
        bucket = "competitor"
        low_line = None
        # baseline_cvr == 0（窗口内全 0 单）时 low_line=0：契约公式 cvr<=baseline*(1-band)
        # 字面成立，0 转化竞品词同样应控 bid，不得因基准为 0 而全部放行 hold_test
        if baseline_cvr is not None:
            low_line = baseline_cvr * (1 - t["low_cvr_band"])
        if term_orders <= 0 and term_spend >= t["high_spend_without_orders"]:
            decision, reason = "reduce_bid", "竞品词高耗无单，先控"
        elif basis != "pool" and m_cvr is not None and low_line is not None and m_cvr <= low_line:
            if baseline_cvr > 0:
                decision, reason = "reduce_bid", "竞品词转化明显低于本 ASIN 基准，先控 bid"
            else:
                decision, reason = "reduce_bid", "窗口内全店 0 单背景下竞品词持续消耗无转化，先控 bid"
        else:
            decision, reason = "hold_test", "竞品词表现尚可，加码属策略决策"

    # 5. 无关词
    elif category == "irrelevant_term":
        if term_clicks >= t["negative_min_clicks"] or term_spend >= t["negative_min_spend"]:
            decision, reason = "negative_candidate", "无关词已产生点击/花费，建议 negative exact 止损"
            neg_suggestion = "negative exact"
        else:
            decision, reason = "observe", "无关碎词，点击花费极低，进低量池汇总监控"
            basis = "pool"

    # 6. 相关类低量池
    elif basis == "pool":
        decision, reason = "observe", "term 与 root 样本均不足，进低量池汇总监控（不逐词决策）"

    # 7. 用 m（term 或 root 指标）判
    else:
        # 7a. 无订单数据报表（SB/SD）：只做浪费检测
        if not has_orders_data:
            if m_spend >= t["high_spend_without_orders"]:
                decision, reason = "reduce_bid", "报表无订单字段，仅做浪费检测：花费偏高，先控 bid"
            else:
                decision, reason = "hold_test", "报表无订单字段，仅做浪费检测：花费尚可，保持观测"
        elif baseline_cvr is not None and baseline_cvr > 0 and m_cvr is not None:
            high_line = baseline_cvr * (1 + t["high_cvr_band"])
            near_low = baseline_cvr * (1 - t["near_avg_cvr_band"])
            near_high = baseline_cvr * (1 + t["near_avg_cvr_band"])
            low_line = baseline_cvr * (1 - t["low_cvr_band"])
            # "acos 超标" 取放量容忍线（target * max_scale_mult）：与 scale_up 门一致，
            # 避免 1.0~1.15 倍目标区间既不给放量也被降 bid 的自相矛盾。
            acos_over_scale_line = (
                target_acos is not None and m_acos is not None
                and m_acos > target_acos * t["max_target_acos_multiple_for_scale_up"]
            )
            acos_over_target = (
                target_acos is not None and m_acos is not None and m_acos > target_acos
            )
            acos_very_high = (
                target_acos is not None and m_acos is not None
                and m_acos > target_acos * t["very_high_target_acos_multiple"]
            )
            acos_ok_for_scale = (
                target_acos is not None and m_acos is not None
                and m_acos <= target_acos * t["max_target_acos_multiple_for_scale_up"]
            )

            # 7b. 高效
            if m_cvr >= high_line:
                if basis == "term" and m_clicks >= t["min_clicks_for_scale_up"] and acos_ok_for_scale:
                    decision, reason = "scale_up", "CVR 显著高于基准且 ACOS 在放量容忍线内，可放量"
                elif acos_over_scale_line:
                    decision, reason = "reduce_bid", "高转化但成本超标，压 bid 等 CPC 回落"
                elif basis == "root":
                    decision, reason = "hold_test", "词根整体高效，小步提 bid 测试"
                else:
                    # basis=term 但点击未达放量门槛或 ACOS 不可判：结论仍是 hold_test，
                    # 但理由必须如实描述"高于基准"，不能落到 7e 的"介于判定带之间"
                    decision, reason = "hold_test", "CVR 高于基准，但点击未达放量门槛或 ACOS 不可判，保持测试积累样本"
            # 7c. 近基准
            if decision is None and near_low <= m_cvr <= near_high:
                if acos_over_target:
                    decision, reason = "reduce_bid", "CVR 接近基准但 ACOS 高于目标，先控 bid"
                else:
                    decision, reason = "hold_test", "CVR 接近基准且成本可控，保持测试"
            # 7d. 低效
            if decision is None and m_cvr <= low_line:
                zero_order_heavy = m_orders <= 0 and (
                    m_spend >= t["high_spend_without_orders"] or m_clicks >= t["min_clicks_for_priority"]
                )
                if zero_order_heavy:
                    covered = listing_covered(term.get("search_term") or "", listing_context)
                    if (
                        relevance == "high"
                        and category in ATTR_SCENARIO_CATEGORIES
                        and covered is False
                    ):
                        decision = "listing_feedback"
                        reason = "高相关属性/场景需求且 Listing 未覆盖，反馈 Listing（广告侧同时控 bid）"
                    elif relevance == "high":
                        decision, reason = "reduce_bid", "相关但转化不达标，控成本+查承接"
                    else:
                        decision, reason = "negative_candidate", "低相关低效，止损"
                        neg_suggestion = "negative exact"
                elif acos_very_high:
                    decision, reason = "reduce_bid", "ACOS 超过目标的 1.5 倍，先控 bid"
                elif relevance == "low":
                    decision, reason = "negative_candidate", "转化低于基准且相关度低，建议否词止损"
                    neg_suggestion = "negative exact"
                else:
                    decision, reason = "reduce_bid", "低于基准，先小步降 bid"
            # 7e. 介于带间
            if decision is None:
                decision, reason = "hold_test", "CVR 介于判定带之间，保持测试"
        else:
            # baseline CVR 不可用或为 0（报表含订单字段但窗口内全 0 单——新品/挣扎期常见）：
            # 判定带无法计算，退化为契约 7d 精神的浪费检测。0 单高耗词必须给出止损动作
            # （reduce_bid / negative_candidate / listing_feedback），不允许整份报表一律 hold_test。
            # 注：契约 §5 公式在 baseline=0 时 7b/7c 全部退化为恒真，字面执行同样得不到止损
            # 动作，此分支是显式偏离修复（已在交付 deviations 记录）。
            zero_order_heavy = m_orders <= 0 and (
                m_spend >= t["high_spend_without_orders"] or m_clicks >= t["min_clicks_for_priority"]
            )
            if zero_order_heavy:
                covered = listing_covered(term.get("search_term") or "", listing_context)
                if (
                    relevance == "high"
                    and category in ATTR_SCENARIO_CATEGORIES
                    and covered is False
                ):
                    decision = "listing_feedback"
                    reason = "基准 CVR 不可用（窗口内 0 单）；高相关属性/场景需求且 Listing 未覆盖，反馈 Listing（广告侧同时控 bid）"
                elif relevance == "high":
                    decision, reason = "reduce_bid", "基准 CVR 不可用（窗口内 0 单）；相关词 0 单高耗，控成本+查承接"
                else:
                    decision, reason = "negative_candidate", "基准 CVR 不可用（窗口内 0 单）；低相关 0 单高耗，止损"
                    neg_suggestion = "negative exact"
            else:
                decision, reason = "hold_test", "基准 CVR 不可用（窗口内 0 单或指标缺失），未达止损线，保持测试"

    # 8. 兜底（理论不可达；禁止兜底 observe）
    if decision is None:
        decision, reason = "hold_test", "未命中任何规则（兜底），保持测试"

    # 降级规则：窗口信号打架
    if decision == "scale_up" and term.get("trend_flag") == "mixed":
        decision, reason = "hold_test", "窗口信号打架，先稳"

    # listing_feedback 附加位（独立 flag，不占主 decision，除 7d 命中外）
    listing_flag = decision == "listing_feedback"
    if not listing_flag and category in ATTR_SCENARIO_CATEGORIES:
        covered = listing_covered(term.get("search_term") or "", listing_context)
        if covered is False and w7_clicks_rising(term, report_span_days(meta)):
            listing_flag = True

    return {
        "term": term.get("search_term"),
        "root": term.get("root_id"),
        "category": category,
        "relevance": relevance,
        "classification_source": cls.get("source"),
        "decision": decision,
        "basis": basis,
        "confidence": confidence,
        "reason": reason,
        "bucket": bucket,
        "listing_flag": listing_flag,
        "negative_match_suggestion": neg_suggestion,
        "trend": term.get("trend_flag"),
        "match_types": list(term.get("match_types") or []),
        "metrics": term.get("metrics") or {},
    }


def decide_all(workbook: dict, classifications: dict) -> list:
    roots_index = {r.get("root_id"): r for r in workbook.get("roots") or []}
    meta = workbook.get("meta") or {}
    records = []
    for term in workbook.get("terms") or []:
        root = roots_index.get(term.get("root_id"))
        cls = effective_classification(term, root, classifications)
        records.append(decide_term(term, root, cls, meta))
    return records


# ---------------------------------------------------------------------------
# root 级 negative phrase 建议（整词根 irrelevant 且 term_count>=3）
# ---------------------------------------------------------------------------

def build_root_negatives(workbook: dict, classifications: dict, records: list) -> list:
    roots_index = {r.get("root_id"): r for r in workbook.get("roots") or []}
    by_root = {}
    for rec in records:
        by_root.setdefault(rec["root"], []).append(rec)
    out = []
    for root_id, recs in by_root.items():
        root = roots_index.get(root_id)
        if root is None:
            continue
        if int(root.get("term_count") or len(recs)) < 3:
            continue
        if not recs or any(rec["category"] != "irrelevant_term" for rec in recs):
            continue
        # 契约规则 5：root 级建议嵌在阈值命中分支内——成员全部落低量池（observe(pool)）
        # 时不基于碎点击建议整根拦截
        if not any(rec["decision"] == "negative_candidate" for rec in recs):
            continue
        root_total = (root.get("metrics") or {}).get("total") or {}
        out.append({
            "root": root_id,
            "match_type": "negative phrase",
            "reason": "整词根语义无关（全部成员 irrelevant），建议 negative phrase 整根拦截",
            "term_count": int(root.get("term_count") or len(recs)),
            "spend": round(num(root_total.get("spend")), 2),
            "clicks": int(num(root_total.get("clicks"))),
        })
    out.sort(key=lambda item: -item["spend"])
    return out


# ---------------------------------------------------------------------------
# 验收指标 + payload（契约 §5 验收指标 / §6 payload schema）
# ---------------------------------------------------------------------------

def compute_summary(records: list, meta: dict) -> dict:
    decision_counts = {key: 0 for key in DECISION_KEYS}
    decision_spend = {key: 0.0 for key in DECISION_KEYS}
    category_counts = {}
    category_spend = {}
    pool_stats = {"terms": 0, "clicks": 0, "spend": 0.0, "orders": 0}
    pending_terms = 0
    pending_spend = 0.0
    total_terms = len(records)
    total_spend = 0.0
    zero_order_spend = 0.0
    negative_spend = 0.0
    has_orders_data = bool(meta.get("has_orders_data", True))

    for rec in records:
        total = (rec.get("metrics") or {}).get("total") or {}
        spend = num(total.get("spend"))
        clicks = num(total.get("clicks"))
        orders = num(total.get("orders"))
        total_spend += spend

        decision_counts[rec["decision"]] = decision_counts.get(rec["decision"], 0) + 1
        decision_spend[rec["decision"]] = decision_spend.get(rec["decision"], 0.0) + spend
        category_counts[rec["category"]] = category_counts.get(rec["category"], 0) + 1
        category_spend[rec["category"]] = round(category_spend.get(rec["category"], 0.0) + spend, 4)

        if rec["decision"] == "observe" and rec["basis"] == "pool":
            pool_stats["terms"] += 1
            pool_stats["clicks"] += int(clicks)
            pool_stats["spend"] += spend
            pool_stats["orders"] += int(orders)

        # 待判定 = manual_review + observe(basis ∈ {term, root})
        if rec["decision"] == "manual_review" or (
            rec["decision"] == "observe" and rec["basis"] in ("term", "root")
        ):
            pending_terms += 1
            pending_spend += spend

        if has_orders_data and orders <= 0:
            zero_order_spend += spend
        if rec["decision"] == "negative_candidate":
            negative_spend += spend

    pool_stats["spend"] = round(pool_stats["spend"], 2)
    decision_spend = {k: round(v, 2) for k, v in decision_spend.items()}
    baseline = meta.get("baseline") or {}

    return {
        "decision_counts": decision_counts,
        "decision_spend": decision_spend,
        "category_counts": category_counts,
        "category_spend": {k: round(v, 2) for k, v in category_spend.items()},
        "pending_ratio_terms": round(safe_div(pending_terms, total_terms) or 0.0, 4),
        "pending_ratio_spend": round(safe_div(pending_spend, total_spend) or 0.0, 4),
        "pool": pool_stats,
        "waste": {
            "zero_order_spend": round(zero_order_spend, 2) if has_orders_data else None,
            "negative_candidate_spend": round(negative_spend, 2),
        },
        "baseline": {
            "cvr": baseline.get("cvr"),
            "acos": baseline.get("acos"),
            "clicks": baseline.get("clicks"),
            "spend": baseline.get("spend"),
            "orders": baseline.get("orders"),
        },
    }


def window_slice(metrics: dict, key: str) -> dict:
    win = metrics.get(key)
    if not win:
        # 该窗口未计算（自定义 --windows 不含此窗）：显式 null，不捏造 0（契约 §2.4）
        return {"clicks": None, "cvr": None, "acos": None}
    return {
        "clicks": int(num(win.get("clicks"))),
        "cvr": win.get("cvr"),
        "acos": win.get("acos"),
    }


def build_payload(workbook: dict, classifications: dict, records: list,
                  summary: dict, root_negatives: list) -> dict:
    meta = dict(workbook.get("meta") or {})
    meta["run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    terms_payload = []
    for rec in sorted(records, key=lambda r: -num(((r.get("metrics") or {}).get("total") or {}).get("spend"))):
        total = (rec.get("metrics") or {}).get("total") or {}
        metrics = rec.get("metrics") or {}
        terms_payload.append({
            "term": rec["term"],
            "category": rec["category"],
            "relevance": rec["relevance"],
            "decision": rec["decision"],
            "confidence": rec["confidence"],
            "basis": rec["basis"],
            "reason": rec["reason"],
            "root": rec["root"],
            "match_types": rec["match_types"],
            "clicks": int(num(total.get("clicks"))),
            "spend": round(num(total.get("spend")), 2),
            "orders": int(num(total.get("orders"))),
            "sales": round(num(total.get("sales")), 2),
            "cvr": total.get("cvr"),
            "acos": total.get("acos"),
            "cpc": total.get("cpc"),
            "ctr": total.get("ctr"),
            "w7": window_slice(metrics, "w7"),
            "w14": window_slice(metrics, "w14"),
            "w30": window_slice(metrics, "w30"),
            "trend": rec["trend"],
            "listing_flag": bool(rec["listing_flag"]),
            "negative_match_suggestion": rec["negative_match_suggestion"],
        })

    cls_roots = classifications.get("roots") or {}
    roots_payload = []
    for root in workbook.get("roots") or []:
        root_id = root.get("root_id")
        entry = cls_roots.get(root_id) or {}
        hard_tag = root.get("hard_tag")
        category = entry.get("category") or hard_tag or ""
        relevance = entry.get("relevance") or ("high" if hard_tag else "")
        total = (root.get("metrics") or {}).get("total") or {}
        roots_payload.append({
            "root": root_id,
            "category": category,
            "relevance": relevance,
            "term_count": int(root.get("term_count") or 0),
            "clicks": int(num(total.get("clicks"))),
            "spend": round(num(total.get("spend")), 2),
            "orders": int(num(total.get("orders"))),
            "cvr": total.get("cvr"),
            "acos": total.get("acos"),
            "sample_terms": list(root.get("sample_terms") or []),
        })
    roots_payload.sort(key=lambda item: -item["spend"])

    def rec_total(rec: dict) -> dict:
        return (rec.get("metrics") or {}).get("total") or {}

    negatives = [
        {
            "term": rec["term"],
            "match_type": "negative exact",
            "reason": rec["reason"],
            "spend": round(num(rec_total(rec).get("spend")), 2),
            "clicks": int(num(rec_total(rec).get("clicks"))),
        }
        for rec in records if rec["decision"] == "negative_candidate"
    ]
    negatives.sort(key=lambda item: -item["spend"])

    scale_ups = [
        {
            "term": rec["term"],
            "reason": rec["reason"],
            "clicks": int(num(rec_total(rec).get("clicks"))),
            "cvr": rec_total(rec).get("cvr"),
            "acos": rec_total(rec).get("acos"),
        }
        for rec in records if rec["decision"] == "scale_up"
    ]
    scale_ups.sort(key=lambda item: -item["clicks"])

    reduce_bids = [
        {
            "term": rec["term"],
            "reason": rec["reason"],
            "spend": round(num(rec_total(rec).get("spend")), 2),
            "acos": rec_total(rec).get("acos"),
        }
        for rec in records if rec["decision"] == "reduce_bid"
    ]
    reduce_bids.sort(key=lambda item: -item["spend"])

    listing_feedback = [
        {
            "term": rec["term"],
            "insight": f"「{rec['term']}」属于{('属性' if rec['category'] == 'attribute_term' else '场景')}需求，Listing 当前未覆盖该卖点",
            "suggestion": "评估将该属性/场景卖点补进标题/五点/A+，同步观察转化变化",
        }
        for rec in records
        if rec["decision"] == "listing_feedback" or (rec["listing_flag"] and rec["category"] in ATTR_SCENARIO_CATEGORIES)
    ]

    manual_review = [
        {"term": rec["term"], "reason": rec["reason"]}
        for rec in records if rec["decision"] == "manual_review"
    ]

    return {
        "meta": meta,
        "summary": summary,
        "terms": terms_payload,
        "roots": roots_payload,
        "actions": {
            "negatives": negatives,
            "root_negatives": [
                {
                    "root": item["root"],
                    "match_type": item["match_type"],
                    "reason": item["reason"],
                    "term_count": item["term_count"],
                    "spend": item["spend"],
                }
                for item in root_negatives
            ],
            "scale_ups": scale_ups,
            "reduce_bids": reduce_bids,
            "listing_feedback": listing_feedback,
            "manual_review": manual_review,
        },
    }


# ---------------------------------------------------------------------------
# HTML 注入（契约 §6）
# ---------------------------------------------------------------------------

def inject_payload(template_text: str, payload: dict) -> str:
    if PAYLOAD_PLACEHOLDER not in template_text:
        raise ValueError(f"模板缺少占位符 {PAYLOAD_PLACEHOLDER}")
    payload_json = json.dumps(payload, ensure_ascii=False)
    # 把所有 '<' 转义为 '\\u003c'（JSON 字符串内合法转义，JSON.parse 结果不变）：
    # 同时覆盖 </script> 提前闭合与 '<!--'+'<script' 触发的 script-data
    # double-escape 状态。契约 §6 只要求 '</'→'<\/'，此处为其安全超集（偏离已记录）。
    payload_json = payload_json.replace("<", "\\u003c")
    return template_text.replace(PAYLOAD_PLACEHOLDER, payload_json)


# ---------------------------------------------------------------------------
# 渲染：md 主报告 / 明细 csv / 否词清单 csv
# ---------------------------------------------------------------------------

def yaml_scalar(value: Any) -> str:
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def render_markdown(payload: dict, status: str, warnings: list) -> str:
    meta = payload["meta"]
    summary = payload["summary"]
    actions = payload["actions"]
    created = meta.get("run_at") or datetime.now().strftime("%Y-%m-%d %H:%M")
    brand = meta.get("brand") or "未识别品牌"
    asin = meta.get("asin") or ""
    date_range = meta.get("date_range") or ["", ""]
    baseline = summary.get("baseline") or {}
    dc = summary["decision_counts"]
    ds = summary["decision_spend"]

    lines = [
        "---",
        f"created: {yaml_scalar(created)}",
        f"topic: {yaml_scalar(f'{brand} {asin} 搜索词报告分析')}",
        'type: "广告搜索词报告分析"',
        "data_sources:",
        f"  - {yaml_scalar('搜索词报告: ' + str(meta.get('source_file') or '未知'))}",
        f"  - {yaml_scalar('Listing上下文: ' + (str(meta.get('listing_context_source') or ('已提供' if meta.get('listing_context') else '无'))))}",
        f"status: {yaml_scalar(status)}",
        "---",
        "",
        "# 亚马逊搜索词报告分析（v2 词根继承版）",
        "",
        "## 分析对象",
        "",
        f"- 品牌：{brand}　ASIN：{asin}　站点：{meta.get('site') or '—'}　报告类型：{meta.get('report_type') or '—'}",
        f"- 数据区间：{date_range[0]} ~ {date_range[1]}（窗口 {'/'.join(str(w) for w in meta.get('windows') or [])} 天）",
        f"- 目标 ACOS：{fmt_pct(meta.get('target_acos'))}　基准 CVR：{fmt_pct(baseline.get('cvr'))}　基准 ACOS：{fmt_pct(baseline.get('acos'))}",
        "",
        "## 核心结论摘要",
        "",
        "📊 **数据事实**",
        "",
        f"- 唯一搜索词 {len(payload['terms'])} 个，总花费 {fmt_money(sum(t['spend'] for t in payload['terms']))}",
        f"- 决策分布：放量 {dc['scale_up']} / 保持 {dc['hold_test']} / 降bid {dc['reduce_bid']} / 否词 {dc['negative_candidate']} / Listing反馈 {dc['listing_feedback']} / 低量池 {dc['observe']} / 人工复核 {dc['manual_review']}",
        f"- 0 单花费合计：{fmt_money(summary['waste']['zero_order_spend'])}　否词候选花费：{fmt_money(summary['waste']['negative_candidate_spend'])}",
        f"- 待判定占比：词数 {fmt_pct(summary['pending_ratio_terms'])}，花费 {fmt_pct(summary['pending_ratio_spend'])}（目标均 ≤10%）",
        "",
        "💡 **分析推断**",
        "",
        f"- 优先动作：处理 {dc['negative_candidate']} 个否词候选（涉及花费 {fmt_money(ds['negative_candidate'])}）与 {dc['reduce_bid']} 个降 bid 词（涉及花费 {fmt_money(ds['reduce_bid'])}）。",
        f"- 放量机会：{dc['scale_up']} 个词 CVR 显著高于基准且 ACOS 可控，建议小步提 bid 验证。",
        f"- Listing 反馈：{len(actions['listing_feedback'])} 条属性/场景需求信号，建议同步 Listing 优化。",
        "",
    ]
    if warnings:
        lines += ["## ⚠️ 告警", ""]
        lines += [f"- {w}" for w in warnings]
        lines.append("")

    def table(title: str, header: list, rows: list) -> list:
        block = [f"## {title}", "", "| " + " | ".join(header) + " |",
                 "|" + "|".join(["---"] * len(header)) + "|"]
        if rows:
            block += rows
        else:
            block.append("| " + " | ".join(["—"] * len(header)) + " |")
        block.append("")
        return block

    lines += table(
        "否词候选（negative exact）📊",
        ["搜索词", "点击", "花费", "理由"],
        [f"| {item['term']} | {item['clicks']} | {fmt_money(item['spend'])} | {item['reason']} |"
         for item in actions["negatives"][:30]],
    )
    lines += table(
        "词根级否词建议（negative phrase）💡",
        ["词根", "成员词数", "花费", "理由"],
        [f"| {item['root']} | {item['term_count']} | {fmt_money(item['spend'])} | {item['reason']} |"
         for item in actions["root_negatives"]],
    )
    lines += table(
        "放量候选（scale_up）📊",
        ["搜索词", "点击", "CVR", "ACOS", "理由"],
        [f"| {item['term']} | {item['clicks']} | {fmt_pct(item['cvr'])} | {fmt_pct(item['acos'])} | {item['reason']} |"
         for item in actions["scale_ups"][:30]],
    )
    lines += table(
        "降 bid 控成本（reduce_bid）📊",
        ["搜索词", "花费", "ACOS", "理由"],
        [f"| {item['term']} | {fmt_money(item['spend'])} | {fmt_pct(item['acos'])} | {item['reason']} |"
         for item in actions["reduce_bids"][:30]],
    )
    lines += table(
        "Listing 反馈（属性/场景洞察）💡",
        ["搜索词", "洞察", "建议"],
        [f"| {item['term']} | {item['insight']} | {item['suggestion']} |"
         for item in actions["listing_feedback"]],
    )
    brand_rows = [
        f"| {t['term']} | {t['clicks']} | {fmt_money(t['spend'])} | {t['orders']} | {t['decision']} |"
        for t in payload["terms"] if t["category"] == "brand_term"
    ]
    lines += table("品牌词（单列，不与普通词混判）📊", ["搜索词", "点击", "花费", "订单", "决策"], brand_rows)
    comp_rows = [
        f"| {t['term']} | {t['clicks']} | {fmt_money(t['spend'])} | {t['orders']} | {t['decision']} |"
        for t in payload["terms"] if t["category"] == "competitor_term"
    ]
    lines += table("竞品词（单列）📊", ["搜索词", "点击", "花费", "订单", "决策"], comp_rows)
    lines += table(
        "人工复核（manual_review）",
        ["搜索词", "原因"],
        [f"| {item['term']} | {item['reason']} |" for item in actions["manual_review"]],
    )
    pool = summary["pool"]
    lines += [
        "## 低量长尾池（observe, basis=pool）📊",
        "",
        f"- 共 {pool['terms']} 个词：点击 {pool['clicks']} / 花费 {fmt_money(pool['spend'])} / 订单 {pool['orders']}",
        "- **声明**：低量池是 term 与 root 样本都不足的真正碎词，按池汇总监控、明确不逐词决策；不计入待判定。",
        "",
        "## 验收指标",
        "",
        f"- 待判定占比（词数）：{fmt_pct(summary['pending_ratio_terms'])}（目标 ≤10%）",
        f"- 待判定占比（花费）：{fmt_pct(summary['pending_ratio_spend'])}（目标 ≤10%）",
        "",
        "## 方法论脚注",
        "",
        "💡 长尾词按词根聚合继承词根级语义分类与决策（词根样本量足够下结论），避免逐词落入待判定；",
        "数值指标由脚本确定性计算，词根语义分类由 AI 助手结合 Listing 上下文完成。",
        f"数据来源：{meta.get('source_file') or '未知'}；区间 {date_range[0]} ~ {date_range[1]}。",
        "",
    ]
    return "\n".join(lines)


DETAIL_COLUMNS = [
    "term", "category", "relevance", "decision", "confidence", "basis", "reason",
    "root", "match_types", "clicks", "spend", "orders", "sales", "cvr", "acos",
    "cpc", "ctr", "w7_clicks", "w7_cvr", "w7_acos", "w14_clicks", "w14_cvr",
    "w14_acos", "w30_clicks", "w30_cvr", "w30_acos", "trend", "listing_flag",
    "negative_match_suggestion",
]


def write_details_csv(payload: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(DETAIL_COLUMNS)
        for t in payload["terms"]:
            writer.writerow([
                t["term"], t["category"], t["relevance"], t["decision"], t["confidence"],
                t["basis"], t["reason"], t["root"], ",".join(t["match_types"]),
                t["clicks"], t["spend"], t["orders"], t["sales"],
                t["cvr"], t["acos"], t["cpc"], t["ctr"],
                t["w7"]["clicks"], t["w7"]["cvr"], t["w7"]["acos"],
                t["w14"]["clicks"], t["w14"]["cvr"], t["w14"]["acos"],
                t["w30"]["clicks"], t["w30"]["cvr"], t["w30"]["acos"],
                t["trend"], t["listing_flag"], t["negative_match_suggestion"],
            ])


def write_negatives_csv(payload: dict, path: Path, root_negatives_full: Optional[list] = None) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["search_term", "match_type", "reason", "spend", "clicks"])
        for item in payload["actions"]["negatives"]:
            writer.writerow([item["term"], item["match_type"], item["reason"], item["spend"], item["clicks"]])
        # root 段第 5 列必须仍是点击数（成员词数写进 reason），
        # 防止程序化消费把 term_count 误读为 clicks
        root_negatives = root_negatives_full if root_negatives_full is not None else payload["actions"]["root_negatives"]
        if root_negatives:
            writer.writerow([])
            writer.writerow(["# root 级 negative phrase 建议（整词根 irrelevant 且成员数>=3；clicks 列为词根合计点击）", "", "", "", ""])
            for item in root_negatives:
                writer.writerow([
                    item["root"],
                    item["match_type"],
                    f"{item['reason']}（成员 {item['term_count']} 词）",
                    item["spend"],
                    item.get("clicks", ""),
                ])


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage C — 搜索词报告决策与渲染")
    parser.add_argument("workbook", help="Stage A 产出的 workbook.json 路径")
    parser.add_argument("--classifications", required=True, help="Stage B 产出的 root_classifications.json 路径")
    parser.add_argument("--output-dir", required=True, help="输出目录")
    parser.add_argument("--report-title-prefix", help="输出文件前缀，默认 {date}_{brand}_{asin}")
    parser.add_argument("--console-template", help=f"操作台模板路径（默认 {DEFAULT_CONSOLE_TEMPLATE}）")
    parser.add_argument("--report-template", help=f"汇报页模板路径（默认 {DEFAULT_REPORT_TEMPLATE}）")
    return parser.parse_args(argv)


def run(argv: Optional[list] = None) -> dict:
    args = parse_args(argv)
    workbook_path = Path(args.workbook).expanduser().resolve()
    classifications_path = Path(args.classifications).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    console_template_path = Path(args.console_template).expanduser().resolve() if args.console_template else DEFAULT_CONSOLE_TEMPLATE
    report_template_path = Path(args.report_template).expanduser().resolve() if args.report_template else DEFAULT_REPORT_TEMPLATE

    workbook = load_json(workbook_path)
    classifications = load_json(classifications_path)

    # 启动严格校验：覆盖率 + 枚举，fail loud
    validate_classifications(workbook, classifications)

    # 模板前置校验（fail loud，避免跑完决策才发现模板损坏）
    for template_path in (console_template_path, report_template_path):
        if not template_path.exists():
            raise FileNotFoundError(f"HTML 模板不存在：{template_path}")
        if PAYLOAD_PLACEHOLDER not in template_path.read_text(encoding="utf-8"):
            raise ValueError(f"HTML 模板缺少占位符 {PAYLOAD_PLACEHOLDER}：{template_path}")

    meta = workbook.get("meta") or {}
    records = decide_all(workbook, classifications)
    root_negatives = build_root_negatives(workbook, classifications, records)
    summary = compute_summary(records, meta)
    payload = build_payload(workbook, classifications, records, summary, root_negatives)

    warnings = []
    if summary["pending_ratio_terms"] > 0.10:
        warnings.append(
            f"待判定词数占比 {fmt_pct(summary['pending_ratio_terms'])} 超过 10% 目标，需复盘分类或阈值"
        )
    if summary["pending_ratio_spend"] > 0.10:
        warnings.append(
            f"待判定花费占比 {fmt_pct(summary['pending_ratio_spend'])} 超过 10% 目标，需复盘分类或阈值"
        )
    if not meta.get("has_orders_data", True):
        warnings.append("报表无订单/销售字段，本次仅做浪费检测，不输出转化结论（局限已在报告声明）")
    status = "DONE_WITH_CONCERNS" if warnings else "DONE"

    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    prefix = args.report_title_prefix or f"{date_str}_{meta.get('brand') or '未识别品牌'}_{meta.get('asin') or 'UNKNOWN'}"

    report_md_path = output_dir / f"{prefix}_搜索词报告分析.md"
    details_csv_path = output_dir / f"{prefix}_搜索词分析明细.csv"
    negatives_csv_path = output_dir / f"{prefix}_否词清单.csv"
    console_html_path = output_dir / f"{prefix}_搜索词分析操作台.html"
    report_html_path = output_dir / f"{prefix}_搜索词分析汇报.html"
    run_summary_path = output_dir / f"{prefix}_run_summary.json"

    report_md_path.write_text(render_markdown(payload, status, warnings), encoding="utf-8")
    write_details_csv(payload, details_csv_path)
    write_negatives_csv(payload, negatives_csv_path, root_negatives)
    console_html_path.write_text(
        inject_payload(console_template_path.read_text(encoding="utf-8"), payload), encoding="utf-8"
    )
    report_html_path.write_text(
        inject_payload(report_template_path.read_text(encoding="utf-8"), payload), encoding="utf-8"
    )

    run_summary = {
        "status": status,
        "brand": meta.get("brand"),
        "asin": meta.get("asin"),
        "report_type": meta.get("report_type"),
        "generated_at": payload["meta"]["run_at"],
        "term_count": len(records),
        "root_count": len(workbook.get("roots") or []),
        "pending_ratio_terms": summary["pending_ratio_terms"],
        "pending_ratio_spend": summary["pending_ratio_spend"],
        "pending_target": 0.10,
        "pool": summary["pool"],
        "decision_counts": summary["decision_counts"],
        "decision_spend": summary["decision_spend"],
        "category_counts": summary["category_counts"],
        "category_spend": summary["category_spend"],
        "waste": summary["waste"],
        "warnings": warnings,
        "files": {
            "report_md": str(report_md_path),
            "details_csv": str(details_csv_path),
            "negatives_csv": str(negatives_csv_path),
            "console_html": str(console_html_path),
            "report_html": str(report_html_path),
            "run_summary": str(run_summary_path),
        },
    }
    run_summary_path.write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_summary


def main(argv: Optional[list] = None) -> int:
    try:
        run_summary = run(argv)
    except ClassificationValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    print(json.dumps(run_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
