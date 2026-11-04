"""Identidades numéricas y denominadores del análisis; sin PostgreSQL ni APIs."""

from copy import deepcopy
from datetime import date
from decimal import Decimal, getcontext, localcontext
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.analytics import build_analysis, describe_findings
from app.charts import chart_number, comparison_chart, contribution_chart, index_chart
from grain_pipeline.common.config import load_dashboard_database_url
from grain_pipeline.quality.analytics import validate_analytical_rows
from tests.analytical_fixtures import analytical_rows


JULY, AUGUST, SEPTEMBER = date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)


class AnalyticalTests(unittest.TestCase):
    def test_indices_use_selected_base_and_mom_keeps_exact_previous_month(self):
        rows = analytical_rows(overrides={("PMAIZMTUSDM", JULY): "50", ("PMAIZMTUSDM", SEPTEMBER): "150"})
        before = deepcopy(rows)
        result = build_analysis(rows, AUGUST, SEPTEMBER)
        corn = [row for row in result["rows"] if row["series_code"] == "PMAIZMTUSDM"]
        self.assertEqual([row["mxn_index"] for row in corn], [Decimal(100), Decimal(150)])
        self.assertEqual(corn[0]["grain_contribution_mxn"], Decimal(1000))
        self.assertEqual(rows, before)
        self.assertEqual(len(describe_findings(result)), 3)

    def test_symmetric_attribution_reconciles_product_change_and_percentage_points(self):
        rows = analytical_rows(overrides={("PMAIZMTUSDM", AUGUST): "80"})
        for row in rows:
            if row["month"] == AUGUST:
                row["average_fix_mxn_usd"] = Decimal(25)
                row["reference_mxn_t"] = row["grain_price_usd_t"] * Decimal(25)
        result = build_analysis(rows, JULY, AUGUST)
        corn = [row for row in result["rows"] if row["series_code"] == "PMAIZMTUSDM"]
        self.assertIsNone(corn[0]["grain_contribution_mxn"])
        self.assertEqual(corn[1]["grain_contribution_mxn"], Decimal(-450))
        self.assertEqual(corn[1]["fx_contribution_mxn"], Decimal(450))
        self.assertEqual(corn[1]["grain_contribution_pp"] + corn[1]["fx_contribution_pp"], Decimal(0))
        summary = next(row for row in result["summary"] if row["series_code"] == "PMAIZMTUSDM")
        self.assertEqual((summary["international_declines"], summary["cancelled_declines"], summary["cancelled_pct"]), (1, 1, Decimal(100)))

    def test_zero_denominator_is_null_and_one_month_has_zero_cumulative_change(self):
        result = build_analysis(analytical_rows(), JULY, JULY)
        for row in result["summary"]:
            self.assertIsNone(row["cancelled_pct"])
            self.assertEqual(row["cumulative_pct"], 0)
            self.assertEqual(row["excluded_months"], 1)
        with self.assertRaises(ValueError):
            build_analysis(analytical_rows(), date(2025, 1, 1), date(2025, 2, 1))

    def test_decimal_context_is_local_and_inputs_are_preserved(self):
        rows = analytical_rows(overrides={("PMAIZMTUSDM", AUGUST): "123.1234567890123"})
        expected = build_analysis(rows, JULY, SEPTEMBER)
        with localcontext() as context:
            context.prec = 6
            self.assertEqual(build_analysis(rows, JULY, SEPTEMBER), expected)
            self.assertEqual(getcontext().prec, 6)

    def test_dashboard_contract_rejects_missing_duplicate_and_inconsistent_gold(self):
        rows = analytical_rows()
        validate_analytical_rows(rows, JULY, SEPTEMBER)
        invalid = [rows[:-1], rows + [rows[0]]]
        for field, value in (("reference_mxn_t", Decimal(5)), ("observed_days", 1),
                              ("mom_change_pct", Decimal(7)), ("fx_average", Decimal(21)),
                              ("grain_price_usd_t", Decimal("NaN"))):
            modified = deepcopy(rows)
            modified[-1][field] = value
            invalid.append(modified)
        for modified in invalid:
            with self.assertRaises(ValueError):
                validate_analytical_rows(modified, JULY, SEPTEMBER)

    def test_charts_have_expected_traces_and_reject_nonrepresentable_values(self):
        result = build_analysis(analytical_rows(), JULY, SEPTEMBER)
        corn = [row for row in result["rows"] if row["series_code"] == "PMAIZMTUSDM"]
        self.assertEqual(len(index_chart(corn).data), 2)
        self.assertEqual(len(contribution_chart(corn).data), 2)
        self.assertEqual(len(comparison_chart(result["summary"]).data[0].x), 3)
        self.assertIsNone(chart_number(None))
        with self.assertRaises(ValueError):
            chart_number(Decimal("1e10000"))

    def test_readonly_override_is_optional_literal_and_empty_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {}, clear=True):
            env_file = Path(temporary) / "fixture.env"
            env_file.write_text("DATABASE_URL=project-${LITERAL}\n", encoding="utf-8-sig")
            self.assertEqual(load_dashboard_database_url(env_file), "project-${LITERAL}")
            os.environ["READONLY_DATABASE_URL"] = "reader-connection"
            self.assertEqual(load_dashboard_database_url(env_file), "reader-connection")
            os.environ["READONLY_DATABASE_URL"] = ""
            with self.assertRaisesRegex(ValueError, "READONLY_DATABASE_URL"):
                load_dashboard_database_url(env_file)
