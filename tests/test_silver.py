"""Capturas, reglas y preparación Silver sin APIs ni conexiones PostgreSQL."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import date, timezone
from decimal import Decimal
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest

from grain_pipeline.extraction.capture_reader import read_capture
from grain_pipeline.extraction.raw import save_capture, write_json
from grain_pipeline.quality.observations import profile_checks, validate_observations
from grain_pipeline.quality.profiling import profile_observations
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.observations import read_observations
from grain_pipeline.transformations.silver import latest_complete_sample, main, prepare_observations
from tests.fixtures import metadata_record, observations_payload


START, END = date(2026, 7, 1), date(2026, 9, 30)


class CaptureReaderTests(unittest.TestCase):
    """La lectura conserva la relación entre bytes, contexto y payload."""

    def test_capture_hash_context_and_payload_match_the_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = observations_payload(SERIES[0])
            path = save_capture(root, SERIES[0], "observations", payload, START, END)
            capture = read_capture(path, root)
            self.assertEqual(capture["content_sha256"], sha256(path.read_bytes()).hexdigest())
            self.assertEqual(capture["window_start"], START)
            self.assertEqual(capture["captured_at"].tzinfo, timezone.utc)
            self.assertEqual(capture["storage_path"], path.name)
            self.assertEqual(capture["payload"], payload)

    def test_paths_outside_the_bronze_root_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "bronze"
            root.mkdir()
            outside = Path(directory) / "outside.json"
            outside.write_text('{}', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_capture(outside, root)

    def test_invalid_context_dates_and_json_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = save_capture(root, SERIES[0], "observations", observations_payload(SERIES[0]), START, END)
            valid = json.loads(path.read_text(encoding="utf-8"))
            cases = ([], {}, {**valid, "provider": "Other"}, {**valid, "kind": "other"},
                     {**valid, "captured_at_utc": "2026-11-03T20:00:00"},
                     {**valid, "captured_at_utc": None},
                     {**valid, "window_start": "2026-10-01"},
                     {**valid, "window_end": "bad"}, {**valid, "kind": "metadata"})
            for value in cases:
                with self.subTest(value=value):
                    path.write_text(json.dumps(value), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        read_capture(path, root)
            path.write_text('{incomplete', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_capture(path, root)

    def test_metadata_has_no_observation_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = save_capture(root, SERIES[0], "metadata", metadata_record(SERIES[0]))
            capture = read_capture(path, root)
            self.assertIsNone(capture["window_start"])
            self.assertIsNone(capture["window_end"])


class SilverPreparationTests(unittest.TestCase):
    """La transformación devuelve tipos comunes y rechaza el conjunto con incidencias."""

    def test_dates_precision_sorting_and_original_records_are_preserved(self):
        records = read_observations(observations_payload(SERIES[0]), SERIES[0])[::-1]
        before = deepcopy(records)
        result = prepare_observations(records, SERIES[0], START, END)
        self.assertEqual(result[0]["observation_date"], START)
        self.assertEqual(result[0]["value"], Decimal("100.1234567890123456789"))
        self.assertEqual(records, before)

    def test_invalid_or_incomplete_rows_block_preparation(self):
        valid = read_observations(observations_payload(SERIES[0]), SERIES[0])
        cases = ([], valid + [valid[0]], valid[:-1],
                 [{**row, "value": "."} for row in valid],
                 [{**row, "value": "-1"} for row in valid],
                 [{**row, "value": "NaN"} for row in valid],
                 [{**row, "date": "2026-07-15"} for row in valid],
                 [{"date": "2026-06-01", "value": "10"}, *valid])
        for records in cases:
            with self.subTest(records=records):
                with self.assertRaises(ValueError):
                    prepare_observations(records, SERIES[0], START, END)

    def test_daily_dates_are_typed_with_calendar_publication_still_pending(self):
        records = read_observations(observations_payload(SERIES[3]), SERIES[3])
        result = prepare_observations(records, SERIES[3], date(2026, 9, 1), END)
        self.assertEqual(result[0]["observation_date"], date(2026, 9, 1))
        self.assertEqual(result[0]["value"], Decimal("18.1234"))
        self.assertEqual(validate_observations(records, SERIES[3], date(2026, 9, 1), END)["coverage_status"],
                         "pending_banking_calendar")

    def test_missing_common_fields_raise_a_controlled_error(self):
        for records in (None, [None], [{"date": "2026-09-01"}]):
            with self.subTest(records=records):
                with self.assertRaises(ValueError):
                    prepare_observations(records, SERIES[0], START, END)

    def test_archived_real_sample_can_be_prepared_without_network_or_database(self):
        root = Path(__file__).resolve().parents[1] / "docs/evidencias/perfilamiento_inicial"
        total = 0
        for path in root.glob("*_observations.json"):
            capture = read_capture(path, root)
            series = next(item for item in SERIES if item["code"] == capture["series_code"])
            records = read_observations(capture["payload"], series)
            total += len(prepare_observations(records, series, capture["window_start"], capture["window_end"]))
        self.assertEqual(total, 30)


class ProfileRuleTests(unittest.TestCase):
    """Los estados de las reglas se determinan fuera de la persistencia."""

    def test_monthly_missing_value_is_failed_for_value_and_coverage(self):
        records = read_observations(observations_payload(SERIES[0]), SERIES[0])
        records[1]["value"] = "."
        checks = {item["rule_code"]: item for item in profile_checks(
            profile_observations(records, SERIES[0], START, END))}
        self.assertEqual(checks["DQ-04"]["status"], "failed")
        self.assertEqual(checks["DQ-08"]["details"]["missing_months"], ["2026-08-01"])
        self.assertNotIn("DQ-09", checks)

    def test_daily_rules_keep_calendar_pending_and_omit_monthly_checks(self):
        records = read_observations(observations_payload(SERIES[3]), SERIES[3])
        checks = {item["rule_code"]: item for item in profile_checks(
            profile_observations(records, SERIES[3], date(2026, 9, 1), END))}
        self.assertEqual(checks["DQ-09"]["status"], "pending")
        self.assertNotIn("DQ-07", checks)
        self.assertNotIn("DQ-08", checks)

    def test_empty_daily_response_is_failed_even_with_zero_row_error_counts(self):
        checks = profile_checks(profile_observations([], SERIES[3], START, END))
        self.assertEqual(checks[0]["rule_code"], "SRC-03")
        self.assertEqual(checks[0]["status"], "failed")


class SilverPreviewTests(unittest.TestCase):
    """El comando recorre archivos locales y presenta resultados sin escribirlos."""

    def test_preview_accepts_four_captures_and_preserves_all_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = root / "samples" / "20261103"
            sample.mkdir(parents=True)
            for series in SERIES:
                start = START if series["provider"] == "FRED" else date(2026, 9, 1)
                save_capture(sample, series, "observations", observations_payload(series), start, END)
            write_json(sample / "profile.json", {"status": "completed"})
            before = {path: path.read_bytes() for path in sample.iterdir()}
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["--bronze-root", str(root)]), 0)
            self.assertIn("11 observaciones", output.getvalue())
            self.assertEqual({path: path.read_bytes() for path in sample.iterdir()}, before)

    def test_finder_ignores_incomplete_folders_and_preview_rejects_missing_series(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            older, newer = root / "samples/20260101", root / "samples/20261103"
            older.mkdir(parents=True)
            newer.mkdir()
            write_json(older / "profile.json", {"status": "completed"})
            self.assertEqual(latest_complete_sample(root), older)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--bronze-root", str(root)]), 1)
