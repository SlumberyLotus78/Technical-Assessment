"""Casos de calendario y formatos que utilizarán las ventanas de consulta."""

from datetime import date
import unittest

from grain_pipeline.common.dates import month_end, parse_date, parse_month, shift_month


class DateOperationsTests(unittest.TestCase):
    def test_source_formats_produce_calendar_dates(self):
        self.assertEqual(parse_date("2024-02-29"), date(2024, 2, 29))
        self.assertEqual(parse_date("29/02/2024", iso=False), date(2024, 2, 29))

    def test_nonstandard_and_impossible_dates_are_rejected(self):
        cases = ((None, True), (42, True), ("2026-2-01", True),
                 ("2026-02-29", True), ("2026-13-01", True),
                 ("31/02/2026", False), ("2026-09-01", False))
        for value, iso in cases:
            with self.subTest(value=value, iso=iso):
                with self.assertRaises(ValueError):
                    parse_date(value, iso=iso)

    def test_month_argument_requires_year_and_month(self):
        self.assertEqual(parse_month("2026-09"), date(2026, 9, 1))
        for value in (None, "2026-9", "09-2026", "2026-09-01", "2026-13"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_month(value)

    def test_month_shift_crosses_year_without_fixed_day_counts(self):
        self.assertEqual(shift_month(date(2026, 1, 31), -1), date(2025, 12, 1))
        self.assertEqual(shift_month(date(2026, 3, 31), -1), date(2026, 2, 1))

    def test_month_end_respects_leap_years(self):
        self.assertEqual(month_end(date(2024, 2, 1)), date(2024, 2, 29))
        self.assertEqual(month_end(date(2025, 2, 1)), date(2025, 2, 28))

    def test_month_shift_rejects_out_of_calendar_range(self):
        for day, delta in ((date.min, -1), (date.max, 1)):
            with self.subTest(day=day, delta=delta):
                with self.assertRaises(ValueError):
                    shift_month(day, delta)
