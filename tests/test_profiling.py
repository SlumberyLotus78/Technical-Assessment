"""Escenarios de calidad y cobertura mensual con registros preparados en memoria."""

from copy import deepcopy
from datetime import date
import unittest

from grain_pipeline.quality.profiling import profile_observations
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.observations import read_observations
from tests.fixtures import observations_payload


START, END = date(2026, 7, 1), date(2026, 9, 30)


class ObservationProfilingTests(unittest.TestCase):
    """Comprueba resultados del perfil sin corregir o completar datos ficticios."""

    def test_complete_monthly_values_preserve_precision_and_do_not_require_sorting(self):
        rows = read_observations(observations_payload(SERIES[0]), SERIES[0])[::-1]
        before = deepcopy(rows)
        result = profile_observations(rows, SERIES[0], START, END)
        self.assertFalse(result["has_issues"])
        self.assertEqual(result["expected_months"], 3)
        self.assertEqual(result["missing_months"], [])
        self.assertEqual(result["value_min"], "100.1234567890123456789")
        self.assertEqual(result["observed_start"], "2026-07-01")
        self.assertEqual(result["observed_end"], "2026-09-01")
        self.assertEqual(rows, before)

    def test_a_missing_value_does_not_count_as_a_month_with_usable_data(self):
        rows = [{"date": "2026-07-01", "value": "100"},
                {"date": "2026-08-01", "value": "."}]
        result = profile_observations(rows, SERIES[0], START, END)
        self.assertTrue(result["has_issues"])
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["missing_values"], 1)
        self.assertEqual(result["missing_months"], ["2026-08-01", "2026-09-01"])
        self.assertEqual(len(rows), 2)  # No fabricamos un registro para septiembre.

    def test_independent_counters_detect_bad_dates_ranges_duplicates_and_values(self):
        rows = [{"date": "2026-07-01", "value": "100"},
                {"date": "2026-07-01", "value": "101"},
                {"date": "bad", "value": "broken"},
                {"date": "2026-06-01", "value": "0"},
                {"date": "2026-07-15", "value": "-2"},
                {"date": "2026-08-01", "value": None}]
        result = profile_observations(rows, SERIES[0], START, END)
        self.assertTrue(result["has_issues"])
        for field in ("invalid_dates", "outside_window", "duplicate_dates",
                      "non_month_start_dates", "invalid_values", "missing_values"):
            with self.subTest(field=field):
                self.assertEqual(result[field], 1)
        self.assertEqual(result["non_positive_values"], 2)
        self.assertEqual(result["numeric_values"], 4)
        self.assertEqual(result["value_min"], "-2")
        self.assertEqual(result["value_max"], "101")

    def test_daily_records_do_not_claim_a_verified_banking_calendar(self):
        # Dos registros correctos no permiten afirmar que el mes FIX esté completo.
        rows = read_observations(observations_payload(SERIES[3]), SERIES[3])
        result = profile_observations(rows, SERIES[3], date(2026, 9, 1), END)
        self.assertFalse(result["has_issues"])
        self.assertEqual(result["coverage_status"], "pending_banking_calendar")
        self.assertIsNone(result["expected_months"])

    def test_empty_responses_are_reported_as_issues(self):
        for series in (SERIES[0], SERIES[3]):
            with self.subTest(provider=series["provider"]):
                result = profile_observations([], series, START, END)
                self.assertTrue(result["has_issues"])
                self.assertEqual(result["rows"], 0)
                self.assertIsNone(result["observed_start"])
                self.assertIsNone(result["value_min"])

    def test_incompatible_windows_or_series_are_rejected(self):
        cases = ((SERIES[0], END, START),
                 (SERIES[0], date(2026, 7, 2), END),
                 (SERIES[0], START, date(2026, 9, 29)),
                 ({**SERIES[0], "frequency": "unknown"}, START, END),
                 ({**SERIES[0], "provider": "Other"}, START, END))
        for series, start, end in cases:
            with self.subTest(series=series["code"], start=start, end=end):
                with self.assertRaises(ValueError):
                    profile_observations([], series, start, end)
