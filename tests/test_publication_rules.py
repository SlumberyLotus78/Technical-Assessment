"""Reglas puras de publicación: continuidad, contexto, duplicados y procedencia."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from grain_pipeline.extraction.capture_reader import read_capture
from grain_pipeline.quality.publication import (
    check_combined_observations, merge_observations, plan_publication,
    validate_capture_set, validate_silver_lineage, validate_stored_gold,
)
from grain_pipeline.sources.catalog import SERIES
from tests.publication_fixtures import publication_capture_files


MONTH, AS_OF = date(2026, 9, 1), date(2026, 11, 3)
RUN = {"load_type": "historical", "start_month": MONTH, "end_month": MONTH}


class PublicationRulesTests(unittest.TestCase):
    """Las reglas no abren PostgreSQL ni leen configuración privada."""

    def test_initial_history_and_incremental_require_different_preconditions(self):
        self.assertEqual(plan_publication(RUN, None, as_of=AS_OF),
                         {"start_month": MONTH, "end_month": MONTH})
        with self.assertRaises(ValueError):
            plan_publication({**RUN, "load_type": "incremental"}, None, as_of=AS_OF)

    def test_revisions_preserve_the_interval_and_extensions_require_continuity(self):
        state = {"start_month": date(2026, 7, 1), "published_through_month": MONTH}
        self.assertEqual(plan_publication(RUN, state, as_of=AS_OF),
                         {"start_month": date(2026, 7, 1), "end_month": MONTH})
        october = {**RUN, "load_type": "incremental", "start_month": date(2026, 10, 1), "end_month": date(2026, 10, 1)}
        self.assertEqual(plan_publication(october, state, as_of=AS_OF)["end_month"], date(2026, 10, 1))
        cases = ({**RUN, "start_month": date(2026, 6, 1)},
                 {**RUN, "start_month": date(2026, 11, 1), "end_month": date(2026, 11, 1)},
                 {**RUN, "start_month": None, "end_month": None})
        for run in cases:
            with self.subTest(run=run), self.assertRaises(ValueError):
                plan_publication(run, state, as_of=date(2026, 12, 1))
        with self.assertRaises(ValueError):
            plan_publication(RUN, None, as_of=MONTH)

    def test_capture_set_requires_unique_valid_metadata_and_planned_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            captures = [read_capture(path, root) for path in publication_capture_files(root, MONTH, MONTH)]
            self.assertEqual(len(validate_capture_set(captures, RUN)["observations"]), 4)
            cases = (captures[1:], captures + [captures[0]],
                     [{**captures[0], "payload": {**captures[0]["payload"], "units": "other"}}, *captures[1:]],
                     [captures[0], {**captures[1], "window_start": date(2026, 8, 1)}, *captures[2:]])
            for candidate in cases:
                with self.subTest(size=len(candidate)), self.assertRaises(ValueError):
                    validate_capture_set(candidate, RUN)

    def test_combined_checks_detect_duplicates_and_missing_grain_months(self):
        row = {"provider": "FRED", "series_code": SERIES[0]["code"], "observation_date": MONTH,
               "value": Decimal(100)}
        checks = check_combined_observations([row, row], MONTH, MONTH)
        self.assertEqual([check["status"] for check in checks], ["failed", "failed"])
        self.assertEqual(checks[0]["details"]["duplicates"][0]["count"], 2)
        self.assertEqual(len(checks[1]["details"]["missing_grain_months"]), 2)

    def test_overlay_keeps_revisions_without_mutating_or_hiding_duplicates(self):
        row = {"provider": "FRED", "series_code": SERIES[0]["code"], "observation_date": MONTH,
               "value": Decimal(100)}
        before = deepcopy(row)
        self.assertEqual(merge_observations([row], [{**row, "value": Decimal(110)}])[0]["value"], Decimal(110))
        self.assertEqual(row, before)
        with self.assertRaises(ValueError):
            merge_observations([row], [row, row])

    def test_silver_lineage_requires_exact_series_date_and_original_value(self):
        capture_id = uuid4()
        row = {"provider": "FRED", "series_code": SERIES[0]["code"], "observation_date": MONTH,
               "value": Decimal(100), "source_capture_id": capture_id}
        originals = {capture_id: {("FRED", SERIES[0]["code"], MONTH): Decimal(100)}}
        validate_silver_lineage([row], originals)
        for changed in ({**row, "value": Decimal(101)}, {**row, "source_capture_id": uuid4()},
                        {**row, "series_code": SERIES[1]["code"]}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                validate_silver_lineage([changed], originals)

    def test_gold_comparison_detects_wrong_values_even_when_counts_match(self):
        row = {"provider": "FRED", "series_code": SERIES[0]["code"], "month": MONTH, "reference_mxn_t": Decimal(2000)}
        gold = {"fx_monthly": [], "grain_reference_monthly": [row]}
        validate_stored_gold(gold, deepcopy(gold))
        with self.assertRaises(ValueError):
            validate_stored_gold(gold, {**gold, "grain_reference_monthly": [{**row, "reference_mxn_t": Decimal(2001)}]})
