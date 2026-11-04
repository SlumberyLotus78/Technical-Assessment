"""Plan incremental y argumentos sin PostgreSQL ni consultas reales."""

from contextlib import redirect_stderr
from datetime import date
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfoNotFoundError

from grain_pipeline.orchestration.incremental import main
from grain_pipeline.orchestration.incremental_plan import plan_incremental_window
from grain_pipeline.quality.incremental import validate_incremental_baseline, validate_review_months
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.metadata import fetch_metadata
from tests.historical_fixtures import CREDENTIALS, historical_session


AS_OF = date(2026, 11, 3)
STATE = {"start_month": date(2009, 1, 1), "published_through_month": date(2026, 9, 1)}


def entries(**kwargs):
    session = historical_session(**kwargs)
    return [{"series": series, "metadata": fetch_metadata(session, series, CREDENTIALS)} for series in SERIES]


class IncrementalPlanningTests(unittest.TestCase):
    """La selección utiliza el avance publicado y todas las fuentes, sin plan de muestra."""

    def test_three_month_review_includes_the_last_three_published_months(self):
        plan = plan_incremental_window(STATE, entries(), as_of=AS_OF, review_months=3)
        self.assertEqual((plan["start_month"], plan["end_month"]), (date(2026, 7, 1), date(2026, 9, 1)))
        self.assertTrue(plan["has_work"])

    def test_new_months_are_added_without_holes_and_zero_review_starts_after_watermark(self):
        for review, start in ((3, date(2026, 7, 1)), (0, date(2026, 10, 1))):
            plan = plan_incremental_window(STATE, entries(latest_month=date(2026, 10, 1)),
                                           as_of=AS_OF, review_months=review)
            self.assertEqual((plan["start_month"], plan["end_month"]), (start, date(2026, 10, 1)))

    def test_zero_review_and_no_new_months_has_no_observation_window(self):
        plan = plan_incremental_window(STATE, entries(), as_of=AS_OF, review_months=0)
        self.assertFalse(plan["has_work"])
        self.assertIsNone(plan["start_month"])
        self.assertIsNone(plan["end_month"])
        capped = plan_incremental_window(STATE, entries(latest_month=date(2026, 10, 1)),
                                         as_of=AS_OF, review_months=0, end_month=date(2026, 9, 1))
        self.assertFalse(capped["has_work"])

    def test_common_month_respects_a_lagging_grain_and_the_last_closed_month(self):
        sources = entries(latest_month=date(2026, 10, 1), latest_by_code={SERIES[1]["code"]: date(2026, 9, 1)})
        self.assertEqual(plan_incremental_window(STATE, sources, as_of=AS_OF, review_months=3)["end_month"], date(2026, 9, 1))
        sources = entries(latest_month=date(2026, 10, 1))
        self.assertEqual(plan_incremental_window(STATE, sources, as_of=date(2026, 10, 15), review_months=3)["end_month"], date(2026, 9, 1))

    def test_revision_window_clips_to_baseline_and_crosses_years(self):
        state = {"start_month": date(2025, 11, 1), "published_through_month": date(2026, 1, 1)}
        for review in (3, 12):
            plan = plan_incremental_window(state, entries(latest_month=date(2026, 2, 1)),
                                           as_of=date(2026, 3, 3), review_months=review)
            self.assertEqual(plan["start_month"], date(2025, 11, 1))
        state["start_month"] = date(2026, 1, 1)
        self.assertEqual(plan_incremental_window(state, entries(), as_of=AS_OF, review_months=3)["start_month"], date(2026, 1, 1))

    def test_source_regression_and_invalid_end_caps_are_rejected(self):
        with self.assertRaises(ValueError):
            plan_incremental_window(STATE, entries(latest_month=date(2026, 8, 1)), as_of=AS_OF, review_months=0)
        sources = entries(latest_month=date(2026, 10, 1))
        self.assertEqual(plan_incremental_window(STATE, sources, as_of=AS_OF, review_months=3,
                                               end_month=date(2026, 9, 1))["end_month"], date(2026, 9, 1))
        for end in (date(2026, 8, 1), date(2026, 11, 1), date(2026, 10, 2)):
            with self.subTest(end=end), self.assertRaises(ValueError):
                plan_incremental_window(STATE, sources, as_of=AS_OF, review_months=3, end_month=end)

    def test_missing_baseline_invalid_review_and_open_watermark_fail(self):
        with self.assertRaises(ValueError):
            validate_incremental_baseline(None, as_of=AS_OF)
        with self.assertRaises(ValueError):
            validate_incremental_baseline(STATE, as_of=date(2026, 9, 15))
        for review in (-1, 13, True, "3"):
            with self.subTest(review=review), self.assertRaises(ValueError):
                validate_review_months(review)


class IncrementalCommandTests(unittest.TestCase):
    """Errores locales se comunican sin imprimir valores privados ni abrir la base."""

    def test_invalid_configuration_review_and_timezone_do_not_connect(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.env"
            with patch.dict("os.environ", {}, clear=True), patch("grain_pipeline.orchestration.incremental.open_connection") as connect:
                with patch("grain_pipeline.orchestration.incremental.logging.basicConfig"), redirect_stderr(io.StringIO()):
                    self.assertEqual(main(["--env-file", str(path)]), 1)
                    self.assertEqual(main(["--review-months", "13"]), 1)
                    with patch("grain_pipeline.orchestration.incremental.ZoneInfo", side_effect=ZoneInfoNotFoundError("fixture")):
                        self.assertEqual(main([]), 1)
                connect.assert_not_called()
