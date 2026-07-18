#!/usr/bin/env /usr/bin/python3
"""Stage C finalize_search_term_report 决策规则与输出单元测试（契约 §5/§6）。"""

from __future__ import annotations

import copy
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
SCRIPTS_DIR = TESTS_DIR.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import finalize_search_term_report as fin  # noqa: E402

WORKBOOK_PATH = FIXTURES_DIR / "finalize_workbook.json"
CLASSIFICATIONS_PATH = FIXTURES_DIR / "finalize_classifications.json"
WORKBOOK_NO_ORDERS_PATH = FIXTURES_DIR / "finalize_workbook_no_orders.json"
CLASSIFICATIONS_NO_ORDERS_PATH = FIXTURES_DIR / "finalize_classifications_no_orders.json"
STUB_TEMPLATE_PATH = FIXTURES_DIR / "finalize_stub_template.html"


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class DecisionRulesTest(unittest.TestCase):
    """逐条覆盖契约 §5 decide 的 1-8 步 + 降级 + 附加位 + confidence。"""

    @classmethod
    def setUpClass(cls):
        cls.workbook = load(WORKBOOK_PATH)
        cls.classifications = load(CLASSIFICATIONS_PATH)
        fin.validate_classifications(cls.workbook, cls.classifications)
        records = fin.decide_all(cls.workbook, cls.classifications)
        cls.by_term = {rec["term"]: rec for rec in records}
        cls.records = records

    def rec(self, term):
        self.assertIn(term, self.by_term, f"fixture 缺少词：{term}")
        return self.by_term[term]

    # -- 规则 1：ASIN 串号词 --
    def test_rule1_asin_term_manual_review(self):
        rec = self.rec("b0test1234")
        self.assertEqual(rec["decision"], "manual_review")
        self.assertEqual(rec["category"], "asin_term")
        self.assertIn("ASIN", rec["reason"])

    # -- 规则 2：needs_listing_check --
    def test_rule2_needs_listing_check_manual_review(self):
        rec = self.rec("obscure gadget thing")
        self.assertEqual(rec["decision"], "manual_review")
        self.assertIn("needs_listing_check", rec["reason"])

    # -- 规则 3：品牌词 --
    def test_rule3_brand_high_spend_zero_orders_manual_review(self):
        rec = self.rec("examplebrand speaker")
        self.assertEqual(rec["decision"], "manual_review")
        self.assertIn("品牌词高耗0单", rec["reason"])

    def test_rule3_brand_normal_hold_test(self):
        rec = self.rec("examplebrand karaoke machine")
        self.assertEqual(rec["decision"], "hold_test")
        self.assertEqual(rec["bucket"], "brand")

    # -- 规则 4：竞品词 --
    def test_rule4_competitor_high_spend_no_orders_reduce_bid(self):
        rec = self.rec("rivalone karaoke machine")
        self.assertEqual(rec["decision"], "reduce_bid")
        self.assertIn("竞品词高耗无单", rec["reason"])

    def test_rule4_competitor_low_cvr_reduce_bid(self):
        rec = self.rec("rivalone portable karaoke")
        self.assertEqual(rec["decision"], "reduce_bid")
        self.assertEqual(rec["basis"], "term")

    def test_rule4_competitor_ok_hold_test(self):
        rec = self.rec("rivalone machine review")
        self.assertEqual(rec["decision"], "hold_test")
        self.assertEqual(rec["bucket"], "competitor")

    # -- 规则 5：无关词 --
    def test_rule5_irrelevant_with_clicks_negative(self):
        rec = self.rec("coloring book for adults")
        self.assertEqual(rec["decision"], "negative_candidate")
        self.assertEqual(rec["negative_match_suggestion"], "negative exact")

    def test_rule5_irrelevant_min_clicks_boundary_negative(self):
        rec = self.rec("coloring book kids")  # 恰好 2 次点击
        self.assertEqual(rec["decision"], "negative_candidate")

    def test_rule5_irrelevant_tiny_goes_to_pool(self):
        rec = self.rec("coloring book")  # 1 点击 / 0.5 花费
        self.assertEqual(rec["decision"], "observe")
        self.assertEqual(rec["basis"], "pool")

    def test_rule5_term_override_precedes_root_category(self):
        rec = self.rec("rivalone coloring")  # 词根竞品，override 为 irrelevant
        self.assertEqual(rec["category"], "irrelevant_term")
        self.assertEqual(rec["decision"], "negative_candidate")
        self.assertEqual(rec["classification_source"], "term_override")

    # -- 规则 6：相关类低量池 --
    def test_rule6_relevant_pool_observe(self):
        for term in ("party lights karaoke", "party lights for karaoke night"):
            rec = self.rec(term)
            self.assertEqual(rec["decision"], "observe")
            self.assertEqual(rec["basis"], "pool")

    # -- 规则 7b：高效 --
    def test_rule7b_scale_up_term_basis(self):
        rec = self.rec("karaoke machine")
        self.assertEqual(rec["decision"], "scale_up")
        self.assertEqual(rec["basis"], "term")
        self.assertEqual(rec["confidence"], "high")  # basis=term 且 clicks>=15

    def test_rule7b_root_inheritance_hold_test(self):
        """决策继承核心用例：长尾词 3 次点击，继承词根级样本下 hold_test。"""
        rec = self.rec("karaoke machine with two microphones")
        self.assertEqual(rec["basis"], "root")
        self.assertEqual(rec["decision"], "hold_test")
        self.assertIn("词根整体高效", rec["reason"])
        self.assertEqual(rec["confidence"], "medium")  # root_clicks>=20

    # -- 规则 7c：近基准 --
    def test_rule7c_near_baseline_high_acos_reduce_bid(self):
        rec = self.rec("karaoke machine for home")
        self.assertEqual(rec["decision"], "reduce_bid")
        self.assertIn("ACOS 高于目标", rec["reason"])

    def test_rule7c_near_baseline_acos_ok_hold_test(self):
        rec = self.rec("karaoke machine bluetooth")
        self.assertEqual(rec["decision"], "hold_test")

    # -- 规则 7d：低效 --
    def test_rule7d_attr_high_relevance_uncovered_listing_feedback(self):
        rec = self.rec("karaoke machine screen lyrics")
        self.assertEqual(rec["decision"], "listing_feedback")
        self.assertTrue(rec["listing_flag"])

    def test_rule7d_high_relevance_covered_reduce_bid(self):
        rec = self.rec("karaoke machine wireless microphone")
        self.assertEqual(rec["decision"], "reduce_bid")
        self.assertIn("相关但转化不达标", rec["reason"])

    def test_rule7d_low_relevance_heavy_negative(self):
        rec = self.rec("karaoke machine rental")
        self.assertEqual(rec["decision"], "negative_candidate")
        self.assertIn("低相关低效", rec["reason"])

    def test_rule7d_very_high_acos_reduce_bid(self):
        rec = self.rec("portable karaoke system")
        self.assertEqual(rec["decision"], "reduce_bid")
        self.assertIn("1.5 倍", rec["reason"])

    def test_rule7d_relevance_low_negative(self):
        rec = self.rec("karaoke maker toy")
        self.assertEqual(rec["decision"], "negative_candidate")

    def test_rule7d_default_reduce_bid(self):
        rec = self.rec("mini karaoke machine")
        self.assertEqual(rec["decision"], "reduce_bid")
        self.assertIn("小步降 bid", rec["reason"])

    # -- 规则 7e：介于带间 --
    def test_rule7e_between_bands_hold_test(self):
        rec = self.rec("karaoke machine home tv")  # CVR 0.1176，介于 near_high 与 high_line 之间
        self.assertEqual(rec["decision"], "hold_test")

    # -- 降级规则：trend mixed --
    def test_downgrade_mixed_trend_scale_up_to_hold_test(self):
        rec = self.rec("karaoke machine duet")
        self.assertEqual(rec["decision"], "hold_test")
        self.assertIn("窗口信号打架", rec["reason"])

    # -- listing_feedback 附加位（不占主 decision） --
    def test_listing_flag_additional_bit_keeps_main_decision(self):
        rec = self.rec("karaoke machine screen touch")
        self.assertEqual(rec["decision"], "scale_up")
        self.assertTrue(rec["listing_flag"])
        self.assertEqual(rec["category"], "attribute_term")  # term_override 生效

    # -- 红线：observe 只允许 pool 路径产生 --
    def test_no_observe_outside_pool(self):
        for rec in self.records:
            if rec["decision"] == "observe":
                self.assertEqual(rec["basis"], "pool", f"{rec['term']} 出现非 pool 的 observe")

    # -- confidence 规则 --
    def test_confidence_low_for_pool(self):
        rec = self.rec("party lights karaoke")
        self.assertEqual(rec["confidence"], "low")


class SummaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workbook = load(WORKBOOK_PATH)
        cls.classifications = load(CLASSIFICATIONS_PATH)
        cls.records = fin.decide_all(cls.workbook, cls.classifications)
        cls.summary = fin.compute_summary(cls.records, cls.workbook["meta"])
        cls.root_negatives = fin.build_root_negatives(cls.workbook, cls.classifications, cls.records)

    def test_decision_counts(self):
        counts = self.summary["decision_counts"]
        self.assertEqual(counts["manual_review"], 3)
        self.assertEqual(counts["scale_up"], 2)
        self.assertEqual(counts["observe"], 3)
        self.assertEqual(counts["negative_candidate"], 5)
        self.assertEqual(counts["listing_feedback"], 1)
        self.assertEqual(counts["hold_test"], 6)
        self.assertEqual(counts["reduce_bid"], 6)
        self.assertEqual(sum(counts.values()), 26)

    def test_pending_ratio(self):
        # 待判定 = manual_review(3) + observe(basis∈{term,root})(0)；26 个唯一词
        self.assertAlmostEqual(self.summary["pending_ratio_terms"], 3 / 26, places=4)
        # 待判定花费 = 4 + 20 + 7 = 31
        total_spend = sum(
            rec["metrics"]["total"]["spend"] for rec in self.records
        )
        self.assertAlmostEqual(self.summary["pending_ratio_spend"], 31.0 / total_spend, places=4)

    def test_pool_stats_excluded_from_pending(self):
        pool = self.summary["pool"]
        self.assertEqual(pool["terms"], 3)
        self.assertEqual(pool["clicks"], 6)
        self.assertAlmostEqual(pool["spend"], 3.8, places=2)
        self.assertEqual(pool["orders"], 0)

    def test_root_negative_phrase_suggestion(self):
        self.assertEqual(len(self.root_negatives), 1)
        item = self.root_negatives[0]
        self.assertEqual(item["root"], "coloring book")
        self.assertEqual(item["match_type"], "negative phrase")
        self.assertEqual(item["term_count"], 3)

    def test_waste_metrics(self):
        waste = self.summary["waste"]
        self.assertIsNotNone(waste["zero_order_spend"])
        # 否词候选花费 = 2.5 + 1.2 + 2 + 16 + 10 = 31.7
        self.assertAlmostEqual(waste["negative_candidate_spend"], 31.7, places=2)


class NoOrdersModeTest(unittest.TestCase):
    """契约 §5 7a：无订单报表只做浪费检测。"""

    @classmethod
    def setUpClass(cls):
        cls.workbook = load(WORKBOOK_NO_ORDERS_PATH)
        cls.classifications = load(CLASSIFICATIONS_NO_ORDERS_PATH)
        records = fin.decide_all(cls.workbook, cls.classifications)
        cls.by_term = {rec["term"]: rec for rec in records}

    def test_high_spend_reduce_bid(self):
        rec = self.by_term["generic term high spend"]
        self.assertEqual(rec["decision"], "reduce_bid")
        self.assertIn("无订单字段", rec["reason"])

    def test_low_spend_hold_test(self):
        rec = self.by_term["generic term low spend"]
        self.assertEqual(rec["decision"], "hold_test")
        self.assertIn("无订单字段", rec["reason"])

    def test_zero_order_spend_not_fabricated(self):
        summary = fin.compute_summary(list(self.by_term.values()), self.workbook["meta"])
        self.assertIsNone(summary["waste"]["zero_order_spend"])


class ValidationTest(unittest.TestCase):
    """启动严格校验：覆盖率 + 枚举，fail loud exit 1。"""

    def setUp(self):
        self.workbook = load(WORKBOOK_PATH)
        self.classifications = load(CLASSIFICATIONS_PATH)

    def test_valid_passes(self):
        fin.validate_classifications(self.workbook, self.classifications)

    def test_missing_root_fails(self):
        broken = copy.deepcopy(self.classifications)
        del broken["roots"]["rivalone"]
        with self.assertRaises(fin.ClassificationValidationError) as ctx:
            fin.validate_classifications(self.workbook, broken)
        self.assertTrue(any("rivalone" in p for p in ctx.exception.problems))

    def test_invalid_category_fails(self):
        broken = copy.deepcopy(self.classifications)
        broken["roots"]["rivalone"]["category"] = "uncertain_term"
        with self.assertRaises(fin.ClassificationValidationError) as ctx:
            fin.validate_classifications(self.workbook, broken)
        self.assertTrue(any("category 非法" in p for p in ctx.exception.problems))

    def test_invalid_relevance_fails(self):
        broken = copy.deepcopy(self.classifications)
        broken["roots"]["rivalone"]["relevance"] = "maybe"
        with self.assertRaises(fin.ClassificationValidationError) as ctx:
            fin.validate_classifications(self.workbook, broken)
        self.assertTrue(any("relevance 非法" in p for p in ctx.exception.problems))

    def test_invalid_override_category_fails(self):
        broken = copy.deepcopy(self.classifications)
        broken["term_overrides"]["rivalone coloring"]["category"] = "banana"
        with self.assertRaises(fin.ClassificationValidationError):
            fin.validate_classifications(self.workbook, broken)

    def test_main_exits_1_on_missing_root(self):
        broken = copy.deepcopy(self.classifications)
        del broken["roots"]["karaoke machine"]
        with tempfile.TemporaryDirectory() as tmp:
            broken_path = Path(tmp) / "broken_classifications.json"
            broken_path.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
            code = fin.main([
                str(WORKBOOK_PATH),
                "--classifications", str(broken_path),
                "--output-dir", tmp,
                "--console-template", str(STUB_TEMPLATE_PATH),
                "--report-template", str(STUB_TEMPLATE_PATH),
            ])
            self.assertEqual(code, 1)


class InjectionTest(unittest.TestCase):
    STUB = '<script id="payload" type="application/json">__PAYLOAD_JSON__</script>'

    def test_placeholder_required(self):
        with self.assertRaises(ValueError):
            fin.inject_payload("<html>no placeholder</html>", {"a": 1})

    def test_script_close_escaped(self):
        html = fin.inject_payload(self.STUB, {"x": "</script>"})
        self.assertNotIn("</script></script>", html)
        # 注入的 JSON 内不允许出现任何字面 '<'（< 转义超集）
        inner = html.split(">", 1)[1].rsplit("</script>", 1)[0]
        self.assertNotIn("<", inner)
        self.assertEqual(json.loads(inner)["x"], "</script>")

    def test_double_escape_comment_script_neutralized(self):
        """'<!--' + '<script' 组合会触发 script-data double-escape 吞掉后续 JS，必须整体转义。"""
        payload = {"meta": {"listing_context": "before <!-- weird snapshot <script src=x> no close"}}
        html = fin.inject_payload(self.STUB, payload)
        inner = html.split(">", 1)[1].rsplit("</script>", 1)[0]
        self.assertNotIn("<!--", inner)
        self.assertNotIn("<script", inner)
        self.assertEqual(json.loads(inner), payload)


class EndToEndTest(unittest.TestCase):
    """完整 finalize：六件产物齐 + run_summary 指标字段齐 + payload 注入成功。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        code = fin.main([
            str(WORKBOOK_PATH),
            "--classifications", str(CLASSIFICATIONS_PATH),
            "--output-dir", cls.tmp.name,
            "--report-title-prefix", "TEST_ExampleBrand_B0TEST1234",
            "--console-template", str(STUB_TEMPLATE_PATH),
            "--report-template", str(STUB_TEMPLATE_PATH),
        ])
        assert code == 0, "finalize main 应返回 0"
        cls.out = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def path(self, suffix):
        return self.out / f"TEST_ExampleBrand_B0TEST1234_{suffix}"

    def test_six_outputs_exist(self):
        for suffix in (
            "搜索词报告分析.md",
            "搜索词分析明细.csv",
            "否词清单.csv",
            "搜索词分析操作台.html",
            "搜索词分析汇报.html",
            "run_summary.json",
        ):
            self.assertTrue(self.path(suffix).exists(), f"缺少输出：{suffix}")

    def test_run_summary_fields(self):
        summary = load(self.path("run_summary.json"))
        for key in (
            "status", "pending_ratio_terms", "pending_ratio_spend", "pool",
            "decision_counts", "decision_spend", "category_counts",
            "category_spend", "waste", "warnings", "files",
        ):
            self.assertIn(key, summary, f"run_summary 缺少字段 {key}")
        # 本 fixture 待判定 3/26 > 10%：不失败但显式告警
        self.assertEqual(summary["status"], "DONE_WITH_CONCERNS")
        self.assertTrue(any("待判定" in w for w in summary["warnings"]))
        self.assertEqual(len(summary["files"]), 6)

    def test_html_payload_injected(self):
        for suffix in ("搜索词分析操作台.html", "搜索词分析汇报.html"):
            html = self.path(suffix).read_text(encoding="utf-8")
            self.assertNotIn("__PAYLOAD_JSON__", html)
            marker = '<script id="payload" type="application/json">'
            self.assertIn(marker, html)
            inner = html.split(marker, 1)[1].split("</script>", 1)[0]
            payload = json.loads(inner)
            self.assertEqual(len(payload["terms"]), 26)
            for key in ("meta", "summary", "terms", "roots", "actions"):
                self.assertIn(key, payload)
            for key in ("negatives", "root_negatives", "scale_ups", "reduce_bids",
                        "listing_feedback", "manual_review"):
                self.assertIn(key, payload["actions"])

    def test_markdown_report_structure(self):
        text = self.path("搜索词报告分析.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"), "缺少 YAML 元数据头")
        self.assertIn("status:", text)
        self.assertIn("📊", text)
        self.assertIn("💡", text)
        self.assertIn("低量长尾池", text)
        self.assertIn("不逐词决策", text)

    def test_negatives_csv_sections(self):
        with open(self.path("否词清单.csv"), encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(rows[0], ["search_term", "match_type", "reason", "spend", "clicks"])
        flat = "\n".join(",".join(r) for r in rows)
        self.assertIn("negative exact", flat)
        self.assertIn("negative phrase", flat)
        self.assertIn("coloring book", flat)

    def test_negatives_csv_root_row_clicks_column_is_clicks(self):
        """root 段第 5 列必须是词根合计点击，不得把 term_count 写进 clicks 列位。"""
        with open(self.path("否词清单.csv"), encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh))
        root_rows = [r for r in rows if r and r[1] == "negative phrase"]
        self.assertEqual(len(root_rows), 1)
        row = root_rows[0]
        workbook = load(WORKBOOK_PATH)
        root = next(r for r in workbook["roots"] if r["root_id"] == row[0])
        self.assertEqual(int(row[4]), root["metrics"]["total"]["clicks"])
        self.assertIn("成员 3 词", row[2])

    def test_details_csv_row_count(self):
        with open(self.path("搜索词分析明细.csv"), encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(len(rows), 27)  # header + 26 词
        self.assertEqual(rows[0][:7], ["term", "category", "relevance", "decision",
                                       "confidence", "basis", "reason"])


def _blk(clicks, spend, orders=0, sales=0.0):
    return {
        "impressions": clicks * 20, "clicks": clicks, "spend": spend,
        "orders": orders, "sales": sales, "ctr": 0.05,
        "cvr": (orders / clicks if clicks else None),
        "acos": (spend / sales if sales else None),
        "cpc": (spend / clicks if clicks else None),
    }


def _metrics(clicks, spend, orders=0, sales=0.0):
    b = _blk(clicks, spend, orders, sales)
    return {"total": dict(b), "w7": dict(b), "w14": dict(b), "w30": dict(b)}


def _term(name, root_id, clicks, spend, orders=0, sales=0.0, trend="stable"):
    return {"search_term": name, "root_id": root_id, "match_types": ["BROAD"],
            "hard_tag": None, "metrics": _metrics(clicks, spend, orders, sales),
            "trend_flag": trend}


def _root(root_id, clicks, spend, orders=0, sales=0.0, term_count=1):
    return {"root_id": root_id, "term_count": term_count,
            "metrics": _metrics(clicks, spend, orders, sales), "hard_tag": None,
            "needs_classification": True}


def _cls(category, relevance, source="root"):
    return {"category": category, "relevance": relevance,
            "needs_listing_check": False, "source": source, "note": ""}


class ZeroOrderBaselineTest(unittest.TestCase):
    """全 0 单报表（baseline.cvr==0）必须退化为浪费检测，不允许一律 hold_test。"""

    def setUp(self):
        self.meta = {
            "baseline": {"clicks": 200, "spend": 100.0, "orders": 0, "sales": 0.0,
                         "cvr": 0.0, "acos": None},
            "target_acos": 0.30, "has_orders_data": True, "listing_context": None,
            "date_range": ["2026-06-08", "2026-07-07"],
        }

    def test_high_relevance_zero_order_heavy_reduce_bid(self):
        term = _term("karaoke machine", "karaoke machine", 40, 60.0)
        rec = fin.decide_term(term, _root("karaoke machine", 40, 60.0), _cls("core_category_term", "high"), self.meta)
        self.assertEqual(rec["decision"], "reduce_bid")
        self.assertIn("0 单", rec["reason"])

    def test_low_relevance_zero_order_heavy_negative(self):
        term = _term("karaoke rental", "karaoke rental", 20, 18.0)
        rec = fin.decide_term(term, _root("karaoke rental", 20, 18.0), _cls("core_category_term", "low"), self.meta)
        self.assertEqual(rec["decision"], "negative_candidate")
        self.assertEqual(rec["negative_match_suggestion"], "negative exact")

    def test_attr_uncovered_listing_feedback(self):
        meta = dict(self.meta)
        meta["listing_context"] = "ExampleBrand karaoke machine bluetooth speaker for party"
        term = _term("waterproof karaoke machine", "karaoke machine", 20, 20.0)
        rec = fin.decide_term(term, _root("karaoke machine", 20, 20.0), _cls("attribute_term", "high"), meta)
        self.assertEqual(rec["decision"], "listing_feedback")

    def test_light_spend_still_hold_test(self):
        term = _term("karaoke mic", "karaoke mic", 8, 5.0)
        rec = fin.decide_term(term, _root("karaoke mic", 8, 5.0), _cls("core_category_term", "high"), self.meta)
        self.assertEqual(rec["decision"], "hold_test")
        self.assertIn("未达止损线", rec["reason"])

    def test_competitor_zero_cvr_reduce_bid(self):
        term = _term("rivalone karaoke", "rivalone", 20, 10.0)
        rec = fin.decide_term(term, _root("rivalone", 20, 10.0), _cls("competitor_term", "low"), self.meta)
        self.assertEqual(rec["decision"], "reduce_bid")


class W7RisingSpanTest(unittest.TestCase):
    """w7 点击上升判定必须按报表实际跨度折算，周报（跨度≤7天）不得判上升。"""

    def _term_with_windows(self, w7, w30):
        t = _term("waterproof karaoke machine", "karaoke machine", w30, 5.0)
        t["metrics"]["w7"]["clicks"] = w7
        t["metrics"]["w30"]["clicks"] = w30
        return t

    def test_seven_day_report_never_rising(self):
        t = self._term_with_windows(3, 3)
        self.assertFalse(fin.w7_clicks_rising(t, 7))

    def test_unknown_span_never_rising(self):
        t = self._term_with_windows(3, 3)
        self.assertFalse(fin.w7_clicks_rising(t, None))

    def test_uniform_14_day_report_not_rising(self):
        # 均匀分布：w7 日均 == w30 日均，不应判上升
        t = self._term_with_windows(3, 6)
        self.assertFalse(fin.w7_clicks_rising(t, 14))

    def test_30_day_report_true_rise_detected(self):
        t = self._term_with_windows(6, 12)  # 近 7 天贡献一半点击
        self.assertTrue(fin.w7_clicks_rising(t, 30))

    def test_min_clicks_guard(self):
        t = self._term_with_windows(1, 1)
        self.assertFalse(fin.w7_clicks_rising(t, 30))

    def test_report_span_days(self):
        self.assertEqual(fin.report_span_days({"date_range": ["2026-07-01", "2026-07-07"]}), 7)
        self.assertEqual(fin.report_span_days({"date_range": ["2026-06-08", "2026-07-07"]}), 30)
        self.assertIsNone(fin.report_span_days({"date_range": []}))
        self.assertIsNone(fin.report_span_days({}))


class RootNegativesPoolGuardTest(unittest.TestCase):
    """成员全部落低量池的 irrelevant 词根不得基于碎点击产出整根 phrase 建议。"""

    def setUp(self):
        self.meta = {
            "baseline": {"clicks": 500, "spend": 100.0, "orders": 40, "sales": 1000.0,
                         "cvr": 0.08, "acos": 0.1},
            "target_acos": 0.30, "has_orders_data": True, "listing_context": None,
            "date_range": ["2026-06-08", "2026-07-07"],
        }
        self.root = _root("fish tank", 3, 2.4, term_count=3)
        self.workbook = {"meta": self.meta, "roots": [self.root], "terms": []}
        self.cls = {"roots": {"fish tank": {"category": "irrelevant_term", "relevance": "low"}}}

    def _records(self, per_term_clicks, per_term_spend):
        records = []
        for name in ("fish tank light", "fish tank decor", "fish tank pump"):
            t = _term(name, "fish tank", per_term_clicks, per_term_spend)
            records.append(fin.decide_term(t, self.root, _cls("irrelevant_term", "low"), self.meta))
        return records

    def test_all_pool_members_no_root_negative(self):
        records = self._records(1, 0.8)  # 均低于 negative_min_clicks/spend → observe(pool)
        self.assertTrue(all(r["decision"] == "observe" for r in records))
        self.assertEqual(fin.build_root_negatives(self.workbook, self.cls, records), [])

    def test_threshold_hit_members_produce_root_negative(self):
        records = self._records(2, 1.5)  # 命中否词阈值 → negative_candidate
        self.assertTrue(all(r["decision"] == "negative_candidate" for r in records))
        out = fin.build_root_negatives(self.workbook, self.cls, records)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["root"], "fish tank")


class WindowSliceTest(unittest.TestCase):
    def test_missing_window_is_null_not_zero(self):
        metrics = {"total": _blk(18, 20.0, 2, 60.0), "w30": _blk(18, 20.0, 2, 60.0)}
        self.assertEqual(fin.window_slice(metrics, "w7"),
                         {"clicks": None, "cvr": None, "acos": None})

    def test_present_window_zero_clicks_stays_zero(self):
        metrics = {"w7": _blk(0, 0.0)}
        self.assertEqual(fin.window_slice(metrics, "w7")["clicks"], 0)


class LoadJsonErrorTest(unittest.TestCase):
    def test_broken_json_error_names_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "broken.json"
            bad.write_text('{"roots": ,}', encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                fin.load_json(bad)
            self.assertIn("broken.json", str(ctx.exception))
            self.assertIn("JSON 解析失败", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
