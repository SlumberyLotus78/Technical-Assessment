"""Calendario de referencia independiente y controles de fechas bancarias FIX."""

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from importlib.resources import files
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from grain_pipeline.quality.calendar import check_fix_coverage
from grain_pipeline.sources.banking_calendar import banking_calendar_for_month
from tests.fixtures import FIX_SAMPLE_MONTH as MONTH, september_fix


class BankingReferenceTests(unittest.TestCase):
    """Las fechas provienen del recurso revisado, sin consultar valores de FIX."""

    def test_september_has_the_exact_expected_dates_and_versioned_evidence(self):
        calendar = banking_calendar_for_month(MONTH)
        self.assertEqual(set(calendar["expected_dates"]), {row["observation_date"] for row in september_fix()})
        self.assertIn("mx-banking-2026-v1:sha256:", calendar["calendar_reference"])
        self.assertEqual(len(calendar["calendar_reference"].split(":")[-1]), 64)
        self.assertIn("https://sidof.segob.gob.mx/notas/5775684", calendar["evidence_urls"])

    def test_banking_closures_and_weekends_are_excluded_without_moving_holidays(self):
        cases = ((4, (2, 3)), (11, (2, 16)), (12, (12, 25)))
        for month, closed_days in cases:
            with self.subTest(month=month):
                expected = banking_calendar_for_month(date(2026, month, 1))["expected_dates"]
                self.assertTrue(all(day.weekday() < 5 for day in expected))
                self.assertTrue(all(date(2026, month, day) not in expected for day in closed_days))
        # El 12 de diciembre cae en sábado: no crea un cierre el lunes 14.
        self.assertIn(date(2026, 12, 14), banking_calendar_for_month(date(2026, 12, 1))["expected_dates"])

    def test_unknown_year_and_invalid_month_do_not_produce_a_fabricated_calendar(self):
        self.assertIsNone(banking_calendar_for_month(date(2027, 1, 1)))
        for value in ("2026-09", date(2026, 9, 2), datetime(2026, 9, 1)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                banking_calendar_for_month(value)

    def test_incompatible_resource_is_an_error_and_crlf_preserves_the_fingerprint(self):
        text = files("grain_pipeline.sources.calendars").joinpath("2026.json").read_text(encoding="utf-8")
        expected = banking_calendar_for_month(MONTH)["calendar_reference"]
        reference = json.loads(text)
        with tempfile.TemporaryDirectory() as directory:
            resource = Path(directory) / "2026.json"
            resource.write_bytes(text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
            with patch("grain_pipeline.sources.banking_calendar.files", return_value=Path(directory)):
                self.assertEqual(banking_calendar_for_month(MONTH)["calendar_reference"], expected)
                for content in ("{bad", "[]", json.dumps({**reference, "year": 2025}),
                                json.dumps({**reference, "closed_dates": ["2026-01-01"] * 2}),
                                json.dumps({**reference, "closed_dates": ["2025-01-01"]})):
                    resource.write_text(content, encoding="utf-8")
                    with self.subTest(content=content), self.assertRaises(ValueError):
                        banking_calendar_for_month(MONTH)


class FixCoverageTests(unittest.TestCase):
    """La igualdad de conteos no sustituye la igualdad de conjuntos."""

    def test_complete_month_passes_and_does_not_modify_inputs(self):
        rows = september_fix()
        original = deepcopy(rows)
        check = check_fix_coverage(rows[::-1], MONTH)
        self.assertEqual(check["rule_code"], "DQ-09")
        self.assertEqual(check["status"], "passed")
        self.assertEqual(check["details"]["expected_days"], 21)
        self.assertEqual(check["details"]["observed_days"], 21)
        self.assertEqual(rows, original)

    def test_same_count_with_a_wrong_date_reports_missing_and_unexpected(self):
        rows = september_fix()
        rows[0] = {**rows[0], "observation_date": date(2026, 9, 16)}
        check = check_fix_coverage(rows, MONTH)
        self.assertEqual(check["status"], "failed")
        self.assertEqual(check["details"]["observed_days"], 21)
        self.assertEqual(check["details"]["missing_dates"], ["2026-09-01"])
        self.assertEqual(check["details"]["unexpected_dates"], ["2026-09-16"])

    def test_duplicates_empty_and_outside_dates_block_the_month(self):
        rows = september_fix()
        cases = (rows + [rows[0]], [], rows + [{**rows[0], "observation_date": date(2026, 10, 1)}])
        for records in cases:
            with self.subTest(size=len(records)):
                self.assertEqual(check_fix_coverage(records, MONTH)["status"], "failed")
        self.assertEqual(check_fix_coverage(rows + [rows[0]], MONTH)["details"]["duplicate_dates"], ["2026-09-01"])

    def test_bad_values_dates_and_series_cannot_certify_coverage(self):
        rows = september_fix()
        changes = ({"value": Decimal("NaN")}, {"value": Decimal("0")}, {"value": 20.0},
                   {"value": None}, {"observation_date": datetime(2026, 9, 1)},
                   {"provider": "FRED"}, {"series_code": "other"})
        for change in changes:
            with self.subTest(change=change):
                check = check_fix_coverage([{**rows[0], **change}, *rows[1:]], MONTH)
                self.assertEqual(check["status"], "failed")
                self.assertEqual(check["details"]["invalid_rows"], 1)

    def test_unreviewed_year_is_pending_and_invalid_rows_still_fail(self):
        month = date(2027, 1, 1)
        check = check_fix_coverage([], month)
        self.assertEqual(check["status"], "pending")
        self.assertIsNone(check["details"]["calendar_reference"])
        self.assertEqual(check_fix_coverage([{}], month)["status"], "failed")
