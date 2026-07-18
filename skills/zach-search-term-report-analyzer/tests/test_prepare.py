#!/usr/bin/env python3
"""Stage A（prepare_search_term_analysis.py）单元测试。

覆盖：词根指派、脏词归并、时间窗切分、缺订单字段容错、
硬标签、0 点击词条剔除、趋势标记、gbk / xlsx 输入。
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent / "scripts"
FIXTURES_DIR = TESTS_DIR / "fixtures"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import prepare_search_term_analysis as prep  # noqa: E402

SMALL_REPORT = FIXTURES_DIR / "prepare_small_report.csv"
NO_ORDERS_REPORT = FIXTURES_DIR / "prepare_no_orders.csv"


def run_prepare(input_file: Path, output_dir: Path, extra_args: "list[str]" = None) -> "dict":
    argv = [
        str(input_file),
        "--asin", "B0TESTASIN",
        "--brand", "ExampleBrand",
        "--site", "US",
        "--target-acos", "0.30",
        "--output-dir", str(output_dir),
    ] + (extra_args or [])
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exit_code = prep.main(argv)
    if exit_code != 0:
        raise AssertionError(f"prepare exit {exit_code}: {buffer.getvalue()}")
    return json.loads((output_dir / "workbook.json").read_text(encoding="utf-8"))


class TokenizeTest(unittest.TestCase):
    def test_lowercase_punct_stopwords(self):
        self.assertEqual(
            prep.tokenize_for_root("Karaoke  Machine for ADULTS!"),
            ["karaoke", "machine", "adults"],
        )

    def test_keeps_digits_and_inner_hyphen(self):
        self.assertEqual(
            prep.tokenize_for_root("all-in-one karaoke 2026"),
            ["all-in-one", "karaoke", "2026"],
        )

    def test_strips_edge_hyphen(self):
        self.assertEqual(prep.tokenize_for_root("-karaoke- machine"), ["karaoke", "machine"])


class RootAssignmentTest(unittest.TestCase):
    def test_bigram_root_requires_three_terms(self):
        clicks = {
            "karaoke machine": 10.0,
            "karaoke machine for adults": 5.0,
            "portable karaoke machine": 3.0,
        }
        roots = prep.assign_roots(clicks)
        self.assertEqual(
            set(roots.values()), {"karaoke machine"},
            "出现词数≥3 的 bigram 应成为词根",
        )

    def test_two_term_bigram_not_qualified_falls_to_unigram(self):
        clicks = {"speaker stand": 3.0, "speaker mount": 2.0}
        roots = prep.assign_roots(clicks)
        self.assertEqual(roots["speaker stand"], "speaker")
        self.assertEqual(roots["speaker mount"], "speaker")

    def test_singleton_root_is_term_itself(self):
        roots = prep.assign_roots({"guitar pedal": 1.0})
        self.assertEqual(roots["guitar pedal"], "guitar pedal")

    def test_highest_click_bigram_wins(self):
        clicks = {
            "blue light kit": 10.0,
            "blue light pro": 10.0,
            "blue light max": 10.0,   # (blue,light) tc=3, clicks=30
            "light kit": 20.0,
            "mini light kit": 20.0,   # (light,kit) tc=3, clicks=10+20+20=50
        }
        roots = prep.assign_roots(clicks)
        self.assertEqual(roots["blue light kit"], "light kit", "应选全局点击最高的合格 bigram")
        self.assertEqual(roots["blue light pro"], "blue light")

    def test_stopword_only_term_is_singleton(self):
        roots = prep.assign_roots({"for the new": 1.0})
        self.assertEqual(roots["for the new"], "for the new")


class HardTagTest(unittest.TestCase):
    def setUp(self):
        self.brand_tokens = prep.brand_tokens_from("ExampleBrand")
        self.threshold = prep.THRESHOLDS["brand_similarity_threshold"]

    def test_exact_brand(self):
        self.assertEqual(
            prep.detect_hard_tag("examplebrand karaoke machine", self.brand_tokens, self.threshold),
            "brand_term",
        )

    def test_fuzzy_brand_typo(self):
        self.assertEqual(
            prep.detect_hard_tag("examplebrnd", self.brand_tokens, self.threshold),
            "brand_term",
        )

    def test_asin_term_wins_over_brand(self):
        self.assertEqual(
            prep.detect_hard_tag("b0abcd1234 examplebrand", self.brand_tokens, self.threshold),
            "asin_term",
        )

    def test_generic_term_untagged(self):
        self.assertIsNone(
            prep.detect_hard_tag("karaoke machine", self.brand_tokens, self.threshold)
        )


class PipelineTest(unittest.TestCase):
    """端到端跑小型 fixture，验证清洗归并、时间窗、词根、硬标签、schema。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="prepare_test_")
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.workbook = run_prepare(SMALL_REPORT, Path(cls._tmp.name))
        cls.terms = {t["search_term"]: t for t in cls.workbook["terms"]}
        cls.roots = {r["root_id"]: r for r in cls.workbook["roots"]}

    def test_dirty_variant_merged(self):
        """脏变体『  Karaoke   Machine 』归并进 karaoke machine，不产生独立词条。"""
        self.assertIn("karaoke machine", self.terms)
        dirty = [t for t in self.terms if t != t.strip() or "  " in t]
        self.assertEqual(dirty, [])
        total = self.terms["karaoke machine"]["metrics"]["total"]
        self.assertEqual(total["clicks"], 33)   # 10+5+8+6+4+0
        self.assertEqual(total["spend"], 35.0)
        self.assertEqual(total["orders"], 2)
        self.assertEqual(
            self.terms["karaoke machine"]["match_types"], ["BROAD", "EXACT", "PHRASE"]
        )

    def test_zero_click_rows_merged_not_dropped(self):
        """0 点击曝光行并入已有词条（展示量计入），不整行丢弃。"""
        total = self.terms["karaoke machine"]["metrics"]["total"]
        self.assertEqual(total["impressions"], 1329)  # 含 999 展示的 0 点击行

    def test_zero_click_only_term_dropped(self):
        """仅有 0 点击 0 花费行的词不产生独立词条，也不进词根。"""
        self.assertNotIn("hdmi cable", self.terms)
        self.assertFalse(any("hdmi" in r for r in self.roots))
        notes = " ".join(self.workbook["meta"]["cleaning_notes"])
        self.assertIn("0 点击", notes)

    def test_window_slicing(self):
        """时间窗以数据最大日期 2026-07-08 为锚：w7 起 07-02、w14 起 06-25、w30 起 06-09。"""
        m = self.terms["karaoke machine"]["metrics"]
        self.assertEqual(m["w7"]["clicks"], 15)    # 07-08 三行：10+5+0
        self.assertEqual(m["w7"]["spend"], 17.0)
        self.assertEqual(m["w7"]["orders"], 1)
        self.assertEqual(m["w14"]["clicks"], 23)   # + 06-25 的 8
        self.assertEqual(m["w14"]["orders"], 2)
        self.assertEqual(m["w30"]["clicks"], 29)   # + 06-09 的 6；06-05 只进 total
        self.assertEqual(m["total"]["clicks"], 33)
        self.assertEqual(self.workbook["meta"]["date_range"], ["2026-06-05", "2026-07-08"])

    def test_derived_metrics_recomputed(self):
        total = self.terms["karaoke machine"]["metrics"]["total"]
        self.assertAlmostEqual(total["cvr"], round(2 / 33, 4))
        self.assertAlmostEqual(total["acos"], round(35.0 / 598.0, 4))
        self.assertAlmostEqual(total["cpc"], round(35.0 / 33, 2))
        # 无销售额时 acos = null
        self.assertIsNone(self.terms["speaker stand"]["metrics"]["total"]["acos"])

    def test_root_assignment_end_to_end(self):
        expected_roots = {
            "karaoke machine", "speaker", "guitar pedal",
            "examplebrand", "examplebrnd", "b0abcd1234 case",
        }
        self.assertEqual(set(self.roots), expected_roots)
        self.assertLess(len(self.roots), len(self.terms))
        km = self.roots["karaoke machine"]
        self.assertEqual(km["term_count"], 3)
        self.assertEqual(
            {t for t in self.terms if self.terms[t]["root_id"] == "karaoke machine"},
            {"karaoke machine", "karaoke machine for adults", "portable karaoke machine"},
        )
        self.assertEqual(self.roots["speaker"]["term_count"], 2)
        # 词根指标 = 成员聚合
        self.assertEqual(km["metrics"]["total"]["clicks"], 33 + 9 + 7)
        self.assertEqual(km["metrics"]["total"]["orders"], 2 + 1)
        self.assertEqual(km["sample_terms"][0], "karaoke machine")

    def test_hard_tags_and_needs_classification(self):
        self.assertEqual(self.terms["examplebrand"]["hard_tag"], "brand_term")
        self.assertEqual(self.terms["examplebrnd"]["hard_tag"], "brand_term")
        self.assertEqual(self.terms["b0abcd1234 case"]["hard_tag"], "asin_term")
        self.assertIsNone(self.terms["karaoke machine"]["hard_tag"])
        self.assertEqual(self.roots["examplebrand"]["hard_tag"], "brand_term")
        self.assertFalse(self.roots["examplebrand"]["needs_classification"])
        self.assertTrue(self.roots["karaoke machine"]["needs_classification"])
        self.assertEqual(
            self.workbook["classification_request"]["roots_to_classify"],
            ["karaoke machine", "speaker", "guitar pedal"],  # 按花费降序，硬标签词根除外
        )
        for term in self.workbook["classification_request"]["top_terms_for_override"]:
            self.assertIsNone(self.terms[term]["hard_tag"])

    def test_trend_flags(self):
        # w7 点击 15 ≥ 8，CVR/ACOS 变化都在 ±20% 带内 → stable
        self.assertEqual(self.terms["karaoke machine"]["trend_flag"], "stable")
        # w7 点击 1 < 8 → insufficient_data
        self.assertEqual(self.terms["guitar pedal"]["trend_flag"], "insufficient_data")

    def test_meta_schema_and_baseline(self):
        meta = self.workbook["meta"]
        for key in (
            "generated_at", "source_file", "brand", "asin", "report_type", "site",
            "target_acos", "date_range", "windows", "baseline", "has_orders_data",
            "listing_context", "thresholds", "unused_fields",
        ):
            self.assertIn(key, meta)
        self.assertEqual(meta["asin"], "B0TESTASIN")
        self.assertEqual(meta["source_file"], SMALL_REPORT.name)
        self.assertNotIn("/", meta["source_file"])
        self.assertEqual(meta["windows"], [7, 14, 30])
        self.assertTrue(meta["has_orders_data"])
        self.assertIsNone(meta["listing_context"])
        self.assertEqual(meta["baseline"]["clicks"], 63)
        self.assertEqual(meta["baseline"]["orders"], 6)
        self.assertAlmostEqual(meta["baseline"]["cvr"], round(6 / 63, 4))
        self.assertEqual(meta["thresholds"]["min_clicks_for_judgement"], 8)
        for entry in self.workbook["terms"]:
            for key in ("search_term", "root_id", "match_types", "hard_tag", "metrics", "trend_flag"):
                self.assertIn(key, entry)
            for window in ("total", "w7", "w14", "w30"):
                block = entry["metrics"][window]
                for field in ("impressions", "clicks", "spend", "orders", "sales", "ctr", "cvr", "acos", "cpc"):
                    self.assertIn(field, block)
        for entry in self.workbook["roots"]:
            for key in ("root_id", "term_count", "sample_terms", "metrics", "hard_tag", "needs_classification"):
                self.assertIn(key, entry)

    def test_terms_sorted_by_spend_desc(self):
        spends = [t["metrics"]["total"]["spend"] for t in self.workbook["terms"]]
        self.assertEqual(spends, sorted(spends, reverse=True))

    def test_roots_for_review_md(self):
        content = (Path(self._tmp.name) / "roots_for_review.md").read_text(encoding="utf-8")
        self.assertIn("root_classifications.json", content)
        self.assertIn("分类任务说明", content)
        self.assertIn("| 1 | karaoke machine |", content)  # 花费最高排第一
        self.assertNotIn("| examplebrand |", content)  # 硬标签词根不进待分类表


class NoOrdersToleranceTest(unittest.TestCase):
    """缺订单/销售字段的报表（如 SB/SD 导出）必须能跑通。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="prepare_test_no_orders_")
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.workbook = run_prepare(NO_ORDERS_REPORT, Path(cls._tmp.name))

    def test_has_orders_data_false(self):
        self.assertFalse(self.workbook["meta"]["has_orders_data"])

    def test_metrics_null_not_fabricated(self):
        for entry in self.workbook["terms"]:
            total = entry["metrics"]["total"]
            self.assertEqual(total["orders"], 0)
            self.assertEqual(total["sales"], 0.0)
            self.assertIsNone(total["cvr"], "无订单数据时 CVR 必须为 null，不得造 0")
            self.assertIsNone(total["acos"])
        baseline = self.workbook["meta"]["baseline"]
        self.assertIsNone(baseline["cvr"])
        self.assertIsNone(baseline["acos"])

    def test_terms_present(self):
        names = {t["search_term"] for t in self.workbook["terms"]}
        self.assertEqual(names, {"karaoke machine", "karaoke system", "karaoke speaker"})


class InputFormatTest(unittest.TestCase):
    """csv 编码探测（gbk）与 xlsx 输入。"""

    def test_gbk_csv(self):
        text = SMALL_REPORT.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="prepare_test_gbk_") as tmp:
            gbk_path = Path(tmp) / "report_gbk.csv"
            gbk_path.write_bytes(text.encode("gbk"))
            workbook = run_prepare(gbk_path, Path(tmp))
            self.assertIn(
                "karaoke machine", {t["search_term"] for t in workbook["terms"]}
            )
            notes = " ".join(workbook["meta"]["cleaning_notes"])
            self.assertIn("gbk", notes)

    def test_xlsx_input(self):
        df = pd.read_csv(SMALL_REPORT, dtype=str, keep_default_na=False)
        with tempfile.TemporaryDirectory(prefix="prepare_test_xlsx_") as tmp:
            xlsx_path = Path(tmp) / "report.xlsx"
            df.to_excel(xlsx_path, index=False)
            workbook = run_prepare(xlsx_path, Path(tmp))
            terms = {t["search_term"]: t for t in workbook["terms"]}
            self.assertEqual(len(terms), 9)
            self.assertEqual(terms["karaoke machine"]["metrics"]["total"]["clicks"], 33)


def run_main_expect_error(argv: "list[str]") -> "tuple[int, str]":
    """跑 prep.main，返回 (exit_code, stderr 文本)。业务错误必须 exit 1 + 「错误：」前缀。"""
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        code = prep.main(argv)
    return code, err.getvalue()


class AsinMismatchTest(unittest.TestCase):
    def test_wrong_asin_fails_loud(self):
        """build_workbook 层抛 ValueError；CLI 层转为「错误：...」+ exit 1，不甩裸 traceback。"""
        with tempfile.TemporaryDirectory(prefix="prepare_test_asin_") as tmp:
            with self.assertRaises(ValueError):
                prep.build_workbook(prep.parse_args([
                    str(SMALL_REPORT),
                    "--asin", "B0WRONG999",
                    "--brand", "ExampleBrand",
                    "--target-acos", "0.30",
                    "--output-dir", tmp,
                ]))
            code, err = run_main_expect_error([
                str(SMALL_REPORT),
                "--asin", "B0WRONG999",
                "--brand", "ExampleBrand",
                "--target-acos", "0.30",
                "--output-dir", tmp,
            ])
            self.assertEqual(code, 1)
            self.assertIn("错误：", err)
            self.assertIn("B0WRONG999", err)


class CliErrorHandlingTest(unittest.TestCase):
    def test_target_acos_is_required(self):
        with tempfile.TemporaryDirectory(prefix="prepare_test_target_acos_") as tmp:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    prep.parse_args([
                        str(SMALL_REPORT),
                        "--asin", "B0TESTASIN",
                        "--brand", "ExampleBrand",
                        "--output-dir", tmp,
                    ])
            self.assertEqual(ctx.exception.code, 2)

    def test_headers_only_csv_clear_error(self):
        """仅表头的空文件：报「没有有效数据行」而非误导性的「缺少核心字段」。"""
        with tempfile.TemporaryDirectory(prefix="prepare_test_empty_") as tmp:
            path = Path(tmp) / "headers_only.csv"
            path.write_text("Date,Customer Search Term,Clicks,Spend\n", encoding="utf-8")
            code, err = run_main_expect_error([
                str(path), "--asin", "B0TESTASIN", "--brand", "ExampleBrand",
                "--target-acos", "0.30", "--output-dir", tmp,
            ])
            self.assertEqual(code, 1)
            self.assertIn("数据行", err)
            self.assertNotIn("缺少核心字段", err)


class NumericIntegrityTest(unittest.TestCase):
    """契约 §2.4：带货币符号/千分位的数值不得被静默清零。"""

    HEADER = "日期,客户搜索词,展示量,点击量,花费,7天总订单数(#),7天总销售额"

    def _write_report(self, tmp: Path, rows: "list[str]") -> Path:
        path = tmp / "report.csv"
        path.write_text(self.HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
        return path

    def test_currency_and_thousands_parsed(self):
        rows = [
            '2026-07-01,karaoke machine,"1,200",30,US$45.60,3,US$1079.70',
            "2026-07-02,karaoke speaker,800,20,$20.00,1,300.00",
        ]
        with tempfile.TemporaryDirectory(prefix="prepare_test_currency_") as tmp:
            workbook = run_prepare(self._write_report(Path(tmp), rows), Path(tmp))
            terms = {t["search_term"]: t for t in workbook["terms"]}
            km = terms["karaoke machine"]["metrics"]["total"]
            self.assertEqual(km["impressions"], 1200)
            self.assertAlmostEqual(km["spend"], 45.6, places=2)
            self.assertAlmostEqual(km["sales"], 1079.7, places=2)
            ks = terms["karaoke speaker"]["metrics"]["total"]
            self.assertAlmostEqual(ks["spend"], 20.0, places=2)
            notes = " ".join(workbook["meta"]["cleaning_notes"])
            self.assertNotIn("解析失败", notes)

    def test_partial_unparseable_values_noted(self):
        rows = [
            "2026-07-01,karaoke machine,500,30,12.50,notanumber,60.0",
            "2026-07-02,karaoke speaker,400,20,10.00,2,50.0",
        ]
        with tempfile.TemporaryDirectory(prefix="prepare_test_badnum_") as tmp:
            workbook = run_prepare(self._write_report(Path(tmp), rows), Path(tmp))
            notes = " ".join(workbook["meta"]["cleaning_notes"])
            self.assertIn("解析失败", notes)
            self.assertIn("orders 1/2", notes)

    def test_core_column_fully_unparseable_fails_loud(self):
        rows = ["2026-07-01,karaoke machine,500,30,badvalue,1,50.0"]
        with tempfile.TemporaryDirectory(prefix="prepare_test_badspend_") as tmp:
            path = self._write_report(Path(tmp), rows)
            code, err = run_main_expect_error([
                str(path), "--asin", "B0TESTASIN", "--brand", "ExampleBrand",
                "--target-acos", "0.30", "--output-dir", tmp,
            ])
            self.assertEqual(code, 1)
            self.assertIn("spend", err)
            self.assertIn("无法解析", err)


if __name__ == "__main__":
    unittest.main()
