#!/usr/bin/env python3
"""Stage A — 搜索词报告预处理：清洗、时间窗聚合、趋势标记、词根聚类、硬标签。

架构契约：references/architecture.md §3（v2）。
产出：
  <output-dir>/workbook.json        供 Stage B（AI 助手语义分类）与 Stage C（决策渲染）
  <output-dir>/roots_for_review.md  待分类词根表（花费降序），供 AI 助手/人分类

用法：
  python3 prepare_search_term_analysis.py <input_file> \
      --asin B0XXXXXXXX --brand <品牌> --target-acos 0.30 [--site US] \
      [--report-type SP] [--windows 7,14,30] [--listing-context-file listing.md] \
      --output-dir <dir>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import clean_search_term_report as cleaner  # noqa: E402  同目录清洗模块（契约要求复用）

# 字段别名表唯一来源（契约 §3.1：必须复用 FIELD_ALIASES）
FIELD_ALIASES = cleaner.FIELD_ALIASES
ASIN_RE = cleaner.ASIN_RE

# 词根聚类停用词表（契约 §3.4）
STOP_WORDS = {
    "for", "with", "the", "a", "an", "of", "to", "in", "on", "and", "or",
    "my", "your", "best", "new",
}

# §5 阈值表实际取值（Stage C 以脚本常量为准，这里写入 workbook.meta 供追溯）
THRESHOLDS = {
    "min_clicks_for_judgement": 8,
    "root_min_clicks_for_judgement": 12,
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
    "negative_min_clicks": 2,
    "negative_min_spend": 1.0,
    "brand_similarity_threshold": 0.85,
}

MIN_BIGRAM_TERM_COUNT = 3   # 词根指派：bigram 出现词数门槛（契约 §3.4）
MIN_UNIGRAM_TERM_COUNT = 2  # 词根指派：unigram 出现词数门槛（契约 §3.4）
SAMPLE_TERMS_LIMIT = 8      # roots.sample_terms 按点击 top8（契约 schema）
TOP_TERMS_FOR_OVERRIDE = 30  # classification_request.top_terms_for_override
RAW_SUM_FIELDS = ("impressions", "clicks", "spend", "orders", "sales")

CATEGORY_ENUM = [
    "brand_term", "competitor_term", "core_category_term",
    "attribute_term", "scenario_term", "irrelevant_term", "asin_term",
]


# ---------------------------------------------------------------------------
# 输入加载（csv utf-8 / utf-8-sig / gbk 探测 + xlsx）
# ---------------------------------------------------------------------------

def detect_csv_encoding(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        raw.decode("gbk")
        return "gbk"
    except UnicodeDecodeError:
        pass
    raise ValueError("无法识别的 CSV 编码（已尝试 utf-8 / utf-8-sig / gbk）")


def load_normalized_frame(
    input_path: Path, brand: "Optional[str]"
) -> "tuple[pd.DataFrame, dict[str, Any], Optional[str]]":
    """加载并清洗输入表。返回 (normalized_df, metadata, csv_encoding)。

    复用 clean_search_term_report.build_normalized_frame；
    gbk 编码 csv 先转写为临时 utf-8 文件再交清洗（其内部 read_csv 仅支持 utf-8 系）。
    """
    suffix = input_path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        df, metadata = cleaner.build_normalized_frame(input_path, brand=brand)
        return df, metadata, None
    if suffix != ".csv":
        raise ValueError(f"不支持的输入类型：{suffix}（仅支持 csv / xlsx）")

    raw = input_path.read_bytes()
    encoding = detect_csv_encoding(raw)
    if encoding in ("utf-8", "utf-8-sig"):
        # pandas C 解析器自动剥离 BOM，已实测可直接复用
        df, metadata = cleaner.build_normalized_frame(input_path, brand=brand)
        return df, metadata, encoding

    text = raw.decode(encoding)
    with tempfile.TemporaryDirectory(prefix="prepare_st_") as tmp_dir:
        tmp_path = Path(tmp_dir) / input_path.name
        tmp_path.write_text(text, encoding="utf-8")
        df, metadata = cleaner.build_normalized_frame(tmp_path, brand=brand)
    metadata["input_file"] = input_path.name
    return df, metadata, encoding


# ---------------------------------------------------------------------------
# 分词 / 硬标签
# ---------------------------------------------------------------------------

def tokenize_for_root(term: str) -> "list[str]":
    """词根聚类分词：小写、去标点（保留数字与词内连字符）、去停用词。"""
    text = str(term).lower()
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    tokens = []
    for token in text.split():
        token = token.strip("-")
        if not token or token in STOP_WORDS:
            continue
        tokens.append(token)
    return tokens


def brand_tokens_from(brand: "Optional[str]") -> "set[str]":
    if not brand:
        return set()
    return {tok for tok in re.findall(r"[a-z0-9]+", str(brand).lower()) if len(tok) > 1}


def token_matches_brand(token: str, brand_tokens: "set[str]", threshold: float) -> bool:
    for candidate in brand_tokens:
        if token == candidate:
            return True
        if len(token) >= 4 and len(candidate) >= 4:
            if SequenceMatcher(None, token, candidate).ratio() >= threshold:
                return True
    return False


def detect_hard_tag(term: str, brand_tokens: "set[str]", threshold: float) -> "Optional[str]":
    """term 级硬标签：asin_term（含 B0 串号）优先，其次 brand_term（模糊匹配）。"""
    if ASIN_RE.search(str(term).upper()):
        return "asin_term"
    for token in re.findall(r"[a-z0-9]+", str(term).lower()):
        if token_matches_brand(token, brand_tokens, threshold):
            return "brand_term"
    return None


# ---------------------------------------------------------------------------
# 词根聚类（契约 §3.4 确定性算法）
# ---------------------------------------------------------------------------

def assign_roots(term_clicks: "dict[str, float]") -> "dict[str, str]":
    """对每个词指派 root_id。

    全局统计每个 unigram / 相邻 bigram 的总点击量与出现词数（unique term count）；
    指派优先级：出现词数≥3 的 bigram（全局点击最高）→ 出现词数≥2 的 unigram
    （全局点击最高）→ 词本身（singleton）。
    """
    unigram_clicks: Counter = Counter()
    unigram_terms: Counter = Counter()
    bigram_clicks: Counter = Counter()
    bigram_terms: Counter = Counter()
    term_tokens: "dict[str, list[str]]" = {}

    for term, clicks in term_clicks.items():
        tokens = tokenize_for_root(term)
        term_tokens[term] = tokens
        for uni in set(tokens):
            unigram_terms[uni] += 1
            unigram_clicks[uni] += clicks
        for big in set(zip(tokens, tokens[1:])):
            bigram_terms[big] += 1
            bigram_clicks[big] += clicks

    assignment: "dict[str, str]" = {}
    for term in term_clicks:
        tokens = term_tokens[term]
        bigram_candidates = [
            big for big in set(zip(tokens, tokens[1:]))
            if bigram_terms[big] >= MIN_BIGRAM_TERM_COUNT
        ]
        if bigram_candidates:
            best = sorted(
                bigram_candidates,
                key=lambda big: (-bigram_clicks[big], " ".join(big)),
            )[0]
            assignment[term] = " ".join(best)
            continue
        unigram_candidates = [
            uni for uni in set(tokens)
            if unigram_terms[uni] >= MIN_UNIGRAM_TERM_COUNT
        ]
        if unigram_candidates:
            best_uni = sorted(
                unigram_candidates,
                key=lambda uni: (-unigram_clicks[uni], uni),
            )[0]
            assignment[term] = best_uni
            continue
        assignment[term] = term  # singleton
    return assignment


# ---------------------------------------------------------------------------
# 指标计算
# ---------------------------------------------------------------------------

def safe_div(numerator: float, denominator: float) -> "Optional[float]":
    if denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def derived_ratios(raw: "dict[str, float]", has_orders: bool, has_sales: bool) -> "dict[str, Optional[float]]":
    """从原始加和复算派生指标（契约：派生指标一律复算，不信报表原值）。"""
    clicks = raw["clicks"]
    return {
        "ctr": safe_div(clicks, raw["impressions"]),
        "cvr": safe_div(raw["orders"], clicks) if has_orders else None,
        "acos": safe_div(raw["spend"], raw["sales"]) if has_sales else None,  # 无 sales 时 acos=null
        "cpc": safe_div(raw["spend"], clicks),
    }


def build_metric_block(raw: "dict[str, float]", has_orders: bool, has_sales: bool) -> "dict[str, Any]":
    ratios = derived_ratios(raw, has_orders, has_sales)
    return {
        "impressions": int(round(raw["impressions"])),
        "clicks": int(round(raw["clicks"])),
        "spend": round(float(raw["spend"]), 2),
        "orders": int(round(raw["orders"])),
        "sales": round(float(raw["sales"]), 2),
        "ctr": None if ratios["ctr"] is None else round(ratios["ctr"], 4),
        "cvr": None if ratios["cvr"] is None else round(ratios["cvr"], 4),
        "acos": None if ratios["acos"] is None else round(ratios["acos"], 4),
        "cpc": None if ratios["cpc"] is None else round(ratios["cpc"], 2),
    }


def pct_change(current: "Optional[float]", base: "Optional[float]") -> "Optional[float]":
    if current is None or base is None or base == 0:
        return None
    return (current - base) / base


def compute_trend_flag(
    raw_by_window: "dict[str, dict[str, float]]",
    windows: "list[int]",
    has_orders: bool,
    has_sales: bool,
) -> str:
    """趋势标记：w7 vs w30 的 CVR / ACOS 变化 > trend_change_band 判定；
    样本（近窗口点击）< min_clicks_for_judgement 判 insufficient_data。
    非默认窗口配置时退化为 最小窗口 vs 最大窗口。
    """
    if 7 in windows and 30 in windows:
        near_key, far_key = "w7", "w30"
    elif len(windows) >= 2:
        near_key, far_key = f"w{min(windows)}", f"w{max(windows)}"
    else:
        return "insufficient_data"

    near_raw = raw_by_window.get(near_key)
    far_raw = raw_by_window.get(far_key)
    if near_raw is None or far_raw is None:
        return "insufficient_data"
    if near_raw["clicks"] < THRESHOLDS["min_clicks_for_judgement"]:
        return "insufficient_data"

    near = derived_ratios(near_raw, has_orders, has_sales)
    far = derived_ratios(far_raw, has_orders, has_sales)
    cvr_change = pct_change(near["cvr"], far["cvr"])
    acos_change = pct_change(near["acos"], far["acos"])
    if cvr_change is None and acos_change is None:
        return "insufficient_data"

    band = THRESHOLDS["trend_change_band"]
    improving = 0
    worsening = 0
    if cvr_change is not None:
        if cvr_change > band:
            improving += 1
        elif cvr_change < -band:
            worsening += 1
    if acos_change is not None:
        if acos_change < -band:
            improving += 1
        elif acos_change > band:
            worsening += 1
    if improving and worsening:
        return "mixed"
    if improving:
        return "improving"
    if worsening:
        return "worsening"
    return "stable"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def filter_to_asin(df: pd.DataFrame, asin: str, cleaning_notes: "list[str]") -> pd.DataFrame:
    """按目标 ASIN 过滤：仅丢弃可识别且不匹配的行；全不匹配则 fail loud。"""
    if "asin" not in df.columns:
        return df
    upper = df["asin"].astype("string").str.upper()
    known = upper.notna()
    if not known.any():
        return df
    matched = known & (upper == asin)
    if not matched.any():
        candidates = upper.dropna().value_counts().head(10)
        raise ValueError(
            f"--asin {asin} 与报表识别到的 ASIN 均不匹配，候选："
            + ", ".join(f"{idx}({int(cnt)}行)" for idx, cnt in candidates.items())
        )
    keep = matched | ~known
    dropped = int(len(df) - int(keep.sum()))
    if dropped:
        cleaning_notes.append(f"丢弃 {dropped} 行非目标 ASIN 数据")
    return df[keep]


def aggregate_term_windows(
    df: pd.DataFrame, windows: "list[int]"
) -> "tuple[dict[str, dict[str, dict[str, float]]], pd.Timestamp]":
    """按标准化搜索词聚合 total + 各时间窗的原始加和。"""
    anchor = df["date"].max().normalize()
    frames = {"total": df}
    for n in windows:
        start = anchor - pd.Timedelta(days=n - 1)
        frames[f"w{n}"] = df[df["date"] >= start]

    total_terms = sorted(df["search_term"].unique())
    term_raws: "dict[str, dict[str, dict[str, float]]]" = {
        term: {} for term in total_terms
    }
    for window_key, frame in frames.items():
        if frame.empty:
            grouped = pd.DataFrame(columns=list(RAW_SUM_FIELDS))
        else:
            grouped = frame.groupby("search_term")[list(RAW_SUM_FIELDS)].sum()
        for term in total_terms:
            if len(grouped) and term in grouped.index:
                row = grouped.loc[term]
                term_raws[term][window_key] = {
                    field: float(row[field]) for field in RAW_SUM_FIELDS
                }
            else:
                term_raws[term][window_key] = {field: 0.0 for field in RAW_SUM_FIELDS}
    return term_raws, anchor


def collect_match_types(df: pd.DataFrame) -> "dict[str, list[str]]":
    if "match_type" not in df.columns:
        return {}
    result: "dict[str, list[str]]" = {}
    for term, series in df.groupby("search_term")["match_type"]:
        values = sorted({
            str(v).upper() for v in series.dropna() if str(v).strip()
        })
        result[term] = values
    return result


def compute_unused_fields(df: pd.DataFrame, mapped_columns: "dict[str, str]") -> "list[str]":
    canonical = set(FIELD_ALIASES) | {
        "search_term_raw", "source_file", "report_type", "brand", "asin",
    }
    unmapped = [col for col in df.columns if col not in canonical]
    provided = set(mapped_columns.values())
    recomputed = [
        f"{field}（报表原值未用，聚合后一律复算）"
        for field in ("ctr", "cpc", "cvr", "acos", "roas")
        if field in provided
    ]
    return unmapped + recomputed


def build_workbook(args: argparse.Namespace) -> "tuple[dict[str, Any], list[str]]":
    input_path = Path(args.input_file).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在：{input_path}")

    windows = parse_windows(args.windows)
    asin = args.asin.strip().upper()
    cleaning_notes: "list[str]" = []

    df, clean_meta, csv_encoding = load_normalized_frame(input_path, args.brand)
    if csv_encoding and csv_encoding != "utf-8":
        cleaning_notes.append(f"CSV 编码探测为 {csv_encoding}")

    # 空表检查必须先于缺字段检查：仅表头的文件经清洗（全空列被剥除）后
    # 会被误报为"缺少核心字段"，误导排障方向
    if df.empty:
        raise ValueError("报表没有有效数据行（可能仅含表头或全为空行），无法分析")

    missing_core = [f for f in ("date", "search_term", "clicks", "spend") if f not in df.columns]
    if missing_core:
        raise ValueError(f"报表缺少核心字段：{missing_core}（字段别名见 FIELD_ALIASES）")

    # 数值诚信（契约 §2.4）：清洗层解析失败的数值（货币符号已容错剥离后仍无法解析的）
    # 不允许静默按 0 计——核心列全部失败即 fail loud，部分失败必须写入 cleaning_notes
    coercion_failures = {
        field: info
        for field, info in (clean_meta.get("numeric_coercion_failures") or {}).items()
        if field in RAW_SUM_FIELDS
    }
    if coercion_failures:
        for field in ("clicks", "spend"):
            info = coercion_failures.get(field)
            if info and info["failed"] >= info["non_empty"]:
                raise ValueError(
                    f"报表 {field} 列 {info['non_empty']} 个非空值全部无法解析为数值，"
                    "疑似格式异常，拒绝按 0 继续分析（请核对源表导出格式）"
                )
        detail = "；".join(
            f"{field} {info['failed']}/{info['non_empty']} 个非空值"
            for field, info in sorted(coercion_failures.items())
        )
        cleaning_notes.append(f"数值解析失败、已按缺失计 0（请核对源表格式）：{detail}")

    df = df[df["search_term"].notna()].copy()
    df = filter_to_asin(df, asin, cleaning_notes)

    no_date = int(df["date"].isna().sum())
    if no_date:
        cleaning_notes.append(f"丢弃 {no_date} 行无法解析日期的数据")
        df = df[df["date"].notna()]
    if df.empty:
        raise ValueError("清洗/过滤后无有效数据行，无法分析")

    # 数值列兜底（缺订单/销售/展示字段容错）；解析失败已在上方显式声明/拦截
    has_orders = "orders" in df.columns and bool(df["orders"].notna().any())
    has_sales = "sales" in df.columns and bool(df["sales"].notna().any())
    for field in RAW_SUM_FIELDS:
        if field not in df.columns:
            df[field] = 0.0
        df[field] = cleaner.to_numeric_lenient(df[field]).fillna(0.0)

    term_raws, anchor = aggregate_term_windows(df, windows)

    # 0 点击（且 0 花费）的曝光词不产生独立词条，仅计数声明
    zero_terms = [
        term for term, raws in term_raws.items()
        if raws["total"]["clicks"] <= 0 and raws["total"]["spend"] <= 0
    ]
    for term in zero_terms:
        term_raws.pop(term)
    if zero_terms:
        cleaning_notes.append(f"剔除 {len(zero_terms)} 个 0 点击 0 花费的纯曝光词（不产生独立词条）")
    if not term_raws:
        raise ValueError("所有搜索词点击与花费均为 0，无可分析词条")

    match_types = collect_match_types(df)

    # 硬标签
    brand_tokens = brand_tokens_from(args.brand)
    threshold = THRESHOLDS["brand_similarity_threshold"]
    hard_tags = {
        term: detect_hard_tag(term, brand_tokens, threshold) for term in term_raws
    }

    # 词根聚类（点击口径 = total）
    term_clicks = {term: raws["total"]["clicks"] for term, raws in term_raws.items()}
    root_assignment = assign_roots(term_clicks)

    # 趋势标记
    trend_flags = {
        term: compute_trend_flag(raws, windows, has_orders, has_sales)
        for term, raws in term_raws.items()
    }

    window_keys = ["total"] + [f"w{n}" for n in windows]

    def spend_key(term: str) -> "tuple[float, float, str]":
        raws = term_raws[term]["total"]
        return (-raws["spend"], -raws["clicks"], term)

    terms_sorted = sorted(term_raws, key=spend_key)
    terms_payload = []
    for term in terms_sorted:
        terms_payload.append({
            "search_term": term,
            "root_id": root_assignment[term],
            "match_types": match_types.get(term, []),
            "hard_tag": hard_tags[term],
            "metrics": {
                key: build_metric_block(term_raws[term][key], has_orders, has_sales)
                for key in window_keys
            },
            "trend_flag": trend_flags[term],
        })

    # 词根级聚合
    root_members: "dict[str, list[str]]" = {}
    for term, root_id in root_assignment.items():
        root_members.setdefault(root_id, []).append(term)

    roots_payload = []
    for root_id, members in root_members.items():
        raw_by_window = {
            key: {field: 0.0 for field in RAW_SUM_FIELDS} for key in window_keys
        }
        for member in members:
            for key in window_keys:
                for field in RAW_SUM_FIELDS:
                    raw_by_window[key][field] += term_raws[member][key][field]
        member_tags = {hard_tags[m] for m in members}
        root_hard_tag = member_tags.pop() if len(member_tags) == 1 else None
        sample_terms = sorted(
            members,
            key=lambda t: (-term_raws[t]["total"]["clicks"], t),
        )[:SAMPLE_TERMS_LIMIT]
        roots_payload.append({
            "root_id": root_id,
            "term_count": len(members),
            "sample_terms": sample_terms,
            "metrics": {
                key: build_metric_block(raw_by_window[key], has_orders, has_sales)
                for key in window_keys
            },
            "hard_tag": root_hard_tag,
            "needs_classification": root_hard_tag is None,
            "_total_spend": raw_by_window["total"]["spend"],
        })
    roots_payload.sort(key=lambda r: (-r["_total_spend"], r["root_id"]))
    for root in roots_payload:
        root.pop("_total_spend")

    # 基准（全词 total 汇总）
    baseline_raw = {field: 0.0 for field in RAW_SUM_FIELDS}
    for raws in term_raws.values():
        for field in RAW_SUM_FIELDS:
            baseline_raw[field] += raws["total"][field]
    baseline_ratios = derived_ratios(baseline_raw, has_orders, has_sales)
    baseline = {
        "clicks": int(round(baseline_raw["clicks"])),
        "spend": round(baseline_raw["spend"], 2),
        "orders": int(round(baseline_raw["orders"])),
        "sales": round(baseline_raw["sales"], 2),
        "cvr": None if baseline_ratios["cvr"] is None else round(baseline_ratios["cvr"], 4),
        "acos": None if baseline_ratios["acos"] is None else round(baseline_ratios["acos"], 4),
    }

    # Listing 上下文（可选增强）
    listing_context = None
    if args.listing_context_file:
        listing_path = Path(args.listing_context_file).expanduser().resolve()
        if not listing_path.exists():
            raise FileNotFoundError(f"--listing-context-file 不存在：{listing_path}")
        listing_raw = listing_path.read_bytes()
        try:
            listing_context = listing_raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            listing_context = listing_raw.decode("gbk")

    report_type = args.report_type or clean_meta.get("report_type") or "UNKNOWN"
    date_min = df["date"].min().strftime("%Y-%m-%d")
    date_max = anchor.strftime("%Y-%m-%d")

    roots_to_classify = [
        root["root_id"] for root in roots_payload if root["needs_classification"]
    ]
    top_terms_for_override = [
        term for term in terms_sorted if hard_tags[term] is None
    ][:TOP_TERMS_FOR_OVERRIDE]

    workbook = {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source_file": input_path.name,
            "brand": args.brand,
            "asin": asin,
            "report_type": report_type,
            "site": args.site,
            "target_acos": args.target_acos,
            "date_range": [date_min, date_max],
            "windows": windows,
            "baseline": baseline,
            "has_orders_data": has_orders,
            "listing_context": listing_context,
            "thresholds": THRESHOLDS,
            "unused_fields": compute_unused_fields(df, clean_meta.get("mapped_columns") or {}),
            "cleaning_notes": cleaning_notes,
        },
        "terms": terms_payload,
        "roots": roots_payload,
        "classification_request": {
            "schema_pointer": "references/term_classification.md",
            "roots_to_classify": roots_to_classify,
            "top_terms_for_override": top_terms_for_override,
        },
    }
    return workbook, cleaning_notes


# ---------------------------------------------------------------------------
# roots_for_review.md 渲染
# ---------------------------------------------------------------------------

def fmt_pct(value: "Optional[float]") -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def fmt_money(value: "Optional[float]") -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def render_roots_for_review(workbook: "dict[str, Any]") -> str:
    meta = workbook["meta"]
    roots = [r for r in workbook["roots"] if r["needs_classification"]]
    # workbook.roots 已按花费降序；此处再保证一次
    roots.sort(key=lambda r: (-r["metrics"]["total"]["spend"], r["root_id"]))
    example = {
        "asin": meta["asin"],
        "classified_by": "ai_assistant",
        "listing_context_source": "workbook.meta.listing_context",
        "roots": {
            (roots[0]["root_id"] if roots else "<root_id>"): {
                "category": "core_category_term",
                "relevance": "high",
                "note": "一句话依据",
                "needs_listing_check": False,
            }
        },
        "term_overrides": {
            "<search_term>": {
                "category": "competitor_term",
                "relevance": "low",
                "note": "个别词偏离词根语义时才点名覆盖",
            }
        },
    }

    lines = []
    lines.append(f"# 词根分类任务 — {meta['brand']} / {meta['asin']}（{meta['site']}）")
    lines.append("")
    lines.append(f"> 生成时间：{meta['generated_at']}　数据窗口：{meta['date_range'][0]} ~ {meta['date_range'][1]}　报告类型：{meta['report_type']}")
    lines.append(f"> 基准 CVR：{fmt_pct(meta['baseline']['cvr'])}　基准 ACOS：{fmt_pct(meta['baseline']['acos'])}　目标 ACOS：{fmt_pct(meta['target_acos'])}")
    listing_state = "已随 workbook.meta.listing_context 提供" if meta["listing_context"] else "未提供（可用本地快照 / fetch_listing_context 补充）"
    lines.append(f"> Listing 上下文：{listing_state}")
    lines.append("")
    lines.append("## 分类任务说明")
    lines.append("")
    lines.append("对下表**每一个** root_id 给出语义分类，写入 `root_classifications.json`：")
    lines.append("")
    lines.append(f"- `category` 枚举（7 选 1）：{' / '.join(CATEGORY_ENUM)}")
    lines.append("- `relevance`：high（本 ASIN 能直接承接该需求）/ medium（部分承接或边缘变体）/ low（基本不承接）")
    lines.append("- `note`：一句话依据")
    lines.append("- **禁止 uncertain**：必须给出 category + relevance；真拿不准的用 `needs_listing_check: true` 标记（应极少，>5% 即算分类失职）")
    lines.append("- 下表每个词根**必须**有条目——Stage C 严格校验覆盖率，缺项即报错退出")
    lines.append("- 个别成员词与词根语义明显不一致时，可在 `term_overrides` 中点名覆盖（可选）")
    lines.append("- 完整 schema 见 `references/term_classification.md`")
    lines.append("")
    lines.append("### root_classifications.json 写法示例")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(example, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append(f"## 待分类词根（共 {len(roots)} 个，按 total 花费降序）")
    lines.append("")
    lines.append("| # | root_id | 成员词数 | 样本词（top5） | 点击 | 花费 | 订单 | CVR | ACOS |")
    lines.append("|---|---------|---------|----------------|------|------|------|-----|------|")
    for idx, root in enumerate(roots, start=1):
        total = root["metrics"]["total"]
        samples = "、".join(root["sample_terms"][:5])
        lines.append(
            f"| {idx} | {root['root_id']} | {root['term_count']} | {samples} "
            f"| {total['clicks']} | {fmt_money(total['spend'])} | {total['orders']} "
            f"| {fmt_pct(total['cvr'])} | {fmt_pct(total['acos'])} |"
        )
    lines.append("")

    override_terms = workbook["classification_request"]["top_terms_for_override"]
    if override_terms:
        term_index = {t["search_term"]: t for t in workbook["terms"]}
        lines.append(f"## 花费 Top{len(override_terms)} 词（顺带检查是否需要 term 级 override）")
        lines.append("")
        lines.append("| # | 搜索词 | 所属词根 | 点击 | 花费 | 订单 | CVR | ACOS |")
        lines.append("|---|--------|----------|------|------|------|-----|------|")
        for idx, term in enumerate(override_terms, start=1):
            entry = term_index[term]
            total = entry["metrics"]["total"]
            lines.append(
                f"| {idx} | {term} | {entry['root_id']} | {total['clicks']} "
                f"| {fmt_money(total['spend'])} | {total['orders']} "
                f"| {fmt_pct(total['cvr'])} | {fmt_pct(total['acos'])} |"
            )
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_windows(text: str) -> "list[int]":
    values = sorted({int(part) for part in str(text).split(",") if part.strip()})
    if not values or any(v <= 0 for v in values):
        raise ValueError(f"--windows 非法：{text}（示例：7,14,30）")
    return values


def parse_args(argv: "Optional[list[str]]" = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage A — 搜索词报告预处理（清洗/时间窗聚合/词根聚类/硬标签）",
    )
    parser.add_argument("input_file", help="原始搜索词报告路径（csv/xlsx）")
    parser.add_argument("--asin", required=True, help="目标 ASIN（B0 开头 10 位）")
    parser.add_argument("--brand", required=True, help="本品牌名（用于 brand_term 硬标签）")
    parser.add_argument("--site", default="US", help="站点，默认 US")
    parser.add_argument("--target-acos", type=float, required=True, help="目标 ACOS，例如 0.30")
    parser.add_argument("--report-type", default=None, help="SP/SB/SD；缺省自动探测")
    parser.add_argument("--windows", default="7,14,30", help="时间窗天数，默认 7,14,30")
    parser.add_argument("--listing-context-file", default=None, help="可选：Listing 上下文 md/txt")
    parser.add_argument("--output-dir", required=True, help="输出目录")
    return parser.parse_args(argv)


def main(argv: "Optional[list[str]]" = None) -> int:
    try:
        return run(argv)
    except (FileNotFoundError, ValueError) as exc:
        # CLI 出错以「错误：...」+ exit 1 呈现（与 finalize 一致），不甩裸 traceback
        print(f"错误：{exc}", file=sys.stderr)
        return 1


def run(argv: "Optional[list[str]]" = None) -> int:
    args = parse_args(argv)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    workbook, cleaning_notes = build_workbook(args)

    workbook_path = output_dir / "workbook.json"
    review_path = output_dir / "roots_for_review.md"
    workbook_path.write_text(
        json.dumps(workbook, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    review_path.write_text(render_roots_for_review(workbook), encoding="utf-8")

    hard_tag_counts = Counter(
        t["hard_tag"] for t in workbook["terms"] if t["hard_tag"]
    )
    summary = {
        "status": "ok",
        "workbook_json": str(workbook_path),
        "roots_for_review_md": str(review_path),
        "terms": len(workbook["terms"]),
        "roots": len(workbook["roots"]),
        "roots_to_classify": len(workbook["classification_request"]["roots_to_classify"]),
        "hard_tag_counts": dict(hard_tag_counts),
        "date_range": workbook["meta"]["date_range"],
        "has_orders_data": workbook["meta"]["has_orders_data"],
        "cleaning_notes": cleaning_notes,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
