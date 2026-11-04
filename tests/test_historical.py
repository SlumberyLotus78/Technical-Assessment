"""Planificación, capturas y perfil histórico sin APIs ni PostgreSQL."""

from contextlib import redirect_stderr
from datetime import date
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfoNotFoundError

from grain_pipeline.extraction.capture_reader import read_capture
from grain_pipeline.extraction.history import capture_historical_metadata, capture_historical_observations
from grain_pipeline.orchestration.historical import main
from grain_pipeline.orchestration.profiling import profile_historical_captures
from grain_pipeline.quality.history import validate_historical_availability, validate_historical_period
from grain_pipeline.sources.banking_calendar import banking_calendar_for_month
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.metadata import fetch_metadata
from grain_pipeline.sources.windows import yearly_query_windows
from grain_pipeline.common.dates import months_between
from tests.historical_fixtures import CREDENTIALS, historical_session


START, END, AS_OF = date(2009, 1, 1), date(2026, 9, 1), date(2026, 11, 3)


class HistoricalPlanningTests(unittest.TestCase):
    """El periodo se valida, se divide y no se reduce silenciosamente."""

    def test_yearly_windows_cover_the_exact_requested_period(self):
        windows = yearly_query_windows(START, END)
        self.assertEqual(len(windows), 18)
        self.assertEqual(windows[0], (START, date(2009, 12, 31)))
        self.assertEqual(windows[-1], (date(2026, 1, 1), date(2026, 9, 30)))
        expanded = [month for first, last in windows for month in months_between(first, last.replace(day=1))]
        self.assertEqual(expanded, months_between(START, END))
        self.assertEqual(yearly_query_windows(date(2024, 2, 1), date(2024, 2, 1)),
                         [(date(2024, 2, 1), date(2024, 2, 29))])

    def test_metadata_availability_and_all_calendars_are_required(self):
        session = historical_session()
        entries = [{"series": series, "metadata": fetch_metadata(session, series, CREDENTIALS)} for series in SERIES]
        validate_historical_availability(entries, START, END, as_of=AS_OF)
        bad = [{**entry, "metadata": {**entry["metadata"], "observation_start": "2010-01-01"}}
               if entry["series"]["provider"] == "FRED" else entry for entry in entries]
        for candidate in (entries[:-1], entries + [entries[0]], bad):
            with self.subTest(size=len(candidate)), self.assertRaises(ValueError):
                validate_historical_availability(candidate, START, END, as_of=AS_OF)
        with self.assertRaisesRegex(ValueError, "2027"):
            validate_historical_availability(entries, date(2027, 1, 1), date(2027, 1, 1), as_of=date(2027, 2, 1))

    def test_daily_metadata_can_end_on_the_last_banking_day_before_month_end(self):
        session = historical_session()
        entries = [{"series": series, "metadata": fetch_metadata(session, series, CREDENTIALS)} for series in SERIES]
        entries[-1]["metadata"]["fechaFin"] = "29/05/2026"
        validate_historical_availability(entries, date(2026, 5, 1), date(2026, 5, 1), as_of=AS_OF)
        entries[-1]["metadata"]["fechaFin"] = "28/05/2026"
        with self.assertRaises(ValueError):
            validate_historical_availability(entries, date(2026, 5, 1), date(2026, 5, 1), as_of=AS_OF)

    def test_open_reversed_and_non_initial_months_are_rejected(self):
        for start, end in ((END, START), (START, AS_OF.replace(day=1)), (date(2026, 9, 2), END)):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                validate_historical_period(start, end, as_of=AS_OF)

    def test_reviewed_resources_preserve_exceptions_and_previous_evidence(self):
        months = months_between(START, END)
        self.assertEqual(sum(len(banking_calendar_for_month(month)["expected_dates"]) for month in months), 4463)
        self.assertNotIn(date(2010, 9, 17), banking_calendar_for_month(date(2010, 9, 1))["expected_dates"])
        self.assertNotIn(date(2024, 10, 1), banking_calendar_for_month(date(2024, 10, 1))["expected_dates"])
        manifest_path = Path(__file__).resolve().parents[1] / "docs/evidencias/calendario_historico/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for record in manifest["resources"]:
            content = (manifest_path.parents[3] / record["file"]).read_text(encoding="utf-8").replace("\r\n", "\n")
            self.assertEqual(sha256(content.encode("utf-8")).hexdigest(), record["sha256_lf"])


class HistoricalCaptureTests(unittest.TestCase):
    """Se conserva cada fragmento y el perfil reúne todos los registros del periodo."""

    def test_metadata_and_yearly_observations_build_a_consolidated_profile(self):
        start, end = date(2025, 12, 1), date(2026, 1, 1)
        session = historical_session()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for series in SERIES:
                paths.append(capture_historical_metadata(session, series, CREDENTIALS, root))
                paths.extend(capture_historical_observations(session, series, CREDENTIALS, root, first, last)
                             for first, last in yearly_query_windows(start, end))
            captures = [read_capture(path, root) for path in paths]
            report = profile_historical_captures(captures, start, end)
            self.assertFalse(report["has_issues"])
            self.assertEqual([profile["rows"] for profile in report["profiles"][:3]], [2, 2, 2])
            self.assertEqual(len(report["fix_monthly_coverage"]), 2)
            self.assertTrue(all(check["status"] == "passed" for check in report["fix_monthly_coverage"]))

    def test_incompatible_metadata_response_is_archived_before_rejection(self):
        session = historical_session()
        session.get.return_value = None
        original = session.get.side_effect
        def wrong_id(*args, **kwargs):
            response = original(*args, **kwargs)
            response.json.return_value["seriess"][0]["id"] = "OTHER"
            return response
        session.get.side_effect = wrong_id
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = capture_historical_metadata(session, SERIES[0], CREDENTIALS, root)
            self.assertEqual(read_capture(path, root)["payload"]["seriess"][0]["id"], "OTHER")

    def test_cli_missing_private_configuration_does_not_connect_or_query_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.env"
            with patch.dict("os.environ", {}, clear=True), patch("grain_pipeline.orchestration.historical.open_connection") as connect:
                with patch("grain_pipeline.orchestration.historical.logging.basicConfig"), redirect_stderr(io.StringIO()):
                    self.assertEqual(main(["--start-month", "2009-01", "--end-month", "2026-09", "--env-file", str(missing)]), 1)
            connect.assert_not_called()

    def test_cli_missing_timezone_returns_a_controlled_error_before_configuration(self):
        with patch("grain_pipeline.orchestration.historical.ZoneInfo", side_effect=ZoneInfoNotFoundError("fixture")):
            with patch("grain_pipeline.orchestration.historical.logging.basicConfig"), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--start-month", "2009-01", "--end-month", "2026-09"]), 1)
