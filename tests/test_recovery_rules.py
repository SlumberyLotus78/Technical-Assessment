"""Decisiones de recuperación y límites de corrección, sin servidor ni red."""

from datetime import date
import unittest

from grain_pipeline.orchestration.recovery import retry_instruction
from grain_pipeline.quality.recovery import recovery_decision
from grain_pipeline.quality.reprocessing import validate_reprocessing_period
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.windows import yearly_query_windows


START, END, TODAY = date(2026, 7, 1), date(2026, 9, 1), date(2026, 11, 3)


class RecoveryRulesTests(unittest.TestCase):
    def attempt(self, **changes):
        return {"status": "running", "start_month": START, "end_month": END, **changes}

    def captures(self, start=START, end=END):
        return [dict(provider=series["provider"], series_code=series["code"], kind=kind, window_start=first, window_end=last)
                for series in SERIES for kind, first, last in [("metadata", None, None),
                    *(("observations", first, last) for first, last in yearly_query_windows(start, end))]]

    def test_only_complete_exact_windows_are_reusable(self):
        captures = self.captures()
        self.assertEqual(recovery_decision(self.attempt(), captures, newer_publication=False)["action"], "reuse_captures")
        for altered in (captures[:-1], captures + [captures[-1]], []):
            self.assertEqual(recovery_decision(self.attempt(), altered, newer_publication=False)["reason"], "incomplete_capture_set")

    def test_newer_publications_and_unplanned_attempts_require_fresh_extraction(self):
        self.assertEqual(recovery_decision(self.attempt(), self.captures(), newer_publication=True)["reason"], "newer_publication")
        self.assertEqual(recovery_decision(self.attempt(start_month=None, end_month=None), [], newer_publication=False)["reason"], "unplanned_window")

    def test_finished_success_is_not_reopened(self):
        for status in ("succeeded", "skipped"):
            self.assertEqual(recovery_decision(self.attempt(status=status), [], newer_publication=True)["action"], "already_completed")
        with self.assertRaises(ValueError):
            recovery_decision(self.attempt(status="unknown"), [], newer_publication=False)

    def test_year_boundary_requires_both_year_windows_for_each_source(self):
        start, end = date(2025, 12, 1), date(2026, 1, 1)
        self.assertEqual(len(self.captures(start, end)), 12)
        self.assertEqual(recovery_decision(self.attempt(start_month=start, end_month=end), self.captures(start, end), newer_publication=False)["action"], "reuse_captures")

    def test_reprocessing_requires_a_published_interval_and_never_extends_it(self):
        state = {"start_month": START, "published_through_month": END}
        validate_reprocessing_period(state, START, END, as_of=TODAY)
        for watermark, start, end in ((None, START, END), (state, date(2026, 6, 1), END),
                                       (state, START, date(2026, 10, 1)), (state, END, START),
                                       (state, START, date(2026, 11, 1))):
            with self.assertRaises(ValueError):
                validate_reprocessing_period(watermark, start, end, as_of=TODAY)

    def test_retry_instruction_distinguishes_initialization_review_and_extension(self):
        self.assertTrue(retry_instruction(self.attempt(), None).startswith("historical "))
        state = {"start_month": START, "published_through_month": END}
        self.assertTrue(retry_instruction(self.attempt(), state).startswith("reprocess "))
        self.assertEqual(retry_instruction(self.attempt(start_month=None, end_month=None), state), "incremental")
