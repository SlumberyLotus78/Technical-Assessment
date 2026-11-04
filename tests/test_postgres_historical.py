"""Histórico completo con PostgreSQL desechable y respuestas HTTP ficticias."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

import psycopg
from psycopg.pq import TransactionStatus
import requests

from grain_pipeline.orchestration.historical import main, run_historical
from grain_pipeline.persistence.catalog import prepare_catalog
from grain_pipeline.persistence.locking import acquire_product_lock
from grain_pipeline.persistence.schema import apply_schema
from tests.historical_fixtures import CREDENTIALS, historical_session
from tests.postgres_support import PostgresTestCase


MONTH, AS_OF = date(2026, 9, 1), date(2026, 11, 3)


class PostgresHistoricalTests(PostgresTestCase):
    """Se ejecutan los módulos reales de extracción y publicación; solo HTTP es simulado."""

    def setUp(self):
        super().setUp()
        apply_schema(self.connection)
        prepare_catalog(self.connection)
        self.connection.commit()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "bronze"

    def run_history(self, session, start=MONTH, end=MONTH, *, as_of=AS_OF):
        return run_historical(self.connection, session, CREDENTIALS, self.root, start, end, as_of=as_of)

    def assert_failed(self, stage, captures):
        self.assertEqual(self.connection.execute("SELECT status, stage FROM ops.runs ORDER BY started_at DESC LIMIT 1").fetchone(),
                         ("failed", stage))
        self.assertEqual(self.connection.execute("SELECT count(*) FROM ops.raw_captures").fetchone()[0], captures)
        for table in ("core.observations", "mart.fx_monthly", "mart.grain_reference_monthly", "ops.watermarks"):
            self.assertEqual(self.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0)

    def test_complete_month_has_durable_artifacts_and_no_open_transaction_during_http(self):
        session = historical_session()
        original = session.get.side_effect
        with psycopg.connect(self.database_url) as other:
            def inspect_request(*args, **kwargs):
                self.assertEqual(self.connection.info.transaction_status, TransactionStatus.IDLE)
                self.assertFalse(acquire_product_lock(other))
                other.commit()
                return original(*args, **kwargs)
            session.get.side_effect = inspect_request
            result = self.run_history(session)
        self.assertEqual(session.get.call_count, 8)
        self.assertEqual(result["silver"]["written"], 24)
        directory = self.root / result["bronze_directory"]
        for name in ("query_plan.json", "extraction_manifest.json", "historical_profile.json", "publication_result.json"):
            self.assertTrue((directory / name).is_file())
        profile = json.loads((directory / "historical_profile.json").read_text(encoding="utf-8"))
        self.assertFalse(profile["has_issues"])
        self.assertEqual(profile["fix_monthly_coverage"][0]["status"], "passed")

    def test_selected_2009_2026_period_reaches_gold_with_all_expected_rows(self):
        session = historical_session()
        result = self.run_history(session, start=date(2009, 1, 1))
        self.assertEqual(session.get.call_count, 76)
        self.assertEqual(result["silver"]["received"], 5102)
        self.assertEqual(result["gold"]["fx_monthly"]["received"], 213)
        self.assertEqual(result["gold"]["grain_reference_monthly"]["received"], 639)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM core.observations WHERE provider = 'Banxico'").fetchone()[0], 4463)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM ops.raw_captures").fetchone()[0], 76)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM mart.grain_reference_monthly WHERE yoy_change_pct = 0").fetchone()[0], 603)
        self.assertEqual(self.connection.execute("SELECT min(reference_mxn_t), max(reference_mxn_t) FROM mart.grain_reference_monthly").fetchone(),
                         (Decimal(2000), Decimal(2000)))

    def test_existing_baseline_rejects_another_initial_history_without_api_calls(self):
        self.run_history(historical_session())
        session = historical_session()
        with self.assertRaises(ValueError):
            self.run_history(session)
        session.get.assert_not_called()
        self.assertEqual(self.connection.execute("SELECT count(*) FROM core.observations").fetchone()[0], 24)
        self.assertEqual(self.connection.execute("SELECT status, stage FROM ops.runs ORDER BY started_at DESC LIMIT 1").fetchone(),
                         ("failed", "planning"))

    def test_exhausted_network_failure_keeps_previous_captures_and_private_error_out_of_logs(self):
        session = historical_session()
        original = session.get.side_effect
        def fail_wheat(url, **kwargs):
            if url.endswith("series/observations") and kwargs["params"]["series_id"] == "PWHEAMTUSDM":
                raise requests.Timeout("fixture-private-url")
            return original(url, **kwargs)
        session.get.side_effect = fail_wheat
        with patch("grain_pipeline.clients.http.time.sleep"), self.assertRaises(RuntimeError):
            self.run_history(session)
        self.assertEqual(session.get.call_count, 8)
        self.assert_failed("extraction", 5)
        self.assertEqual(self.connection.execute("SELECT error_summary FROM ops.runs").fetchone()[0], "RuntimeError")

    def test_incompatible_metadata_is_registered_before_the_contract_fails(self):
        session = historical_session()
        original = session.get.side_effect
        def wrong_unit(*args, **kwargs):
            response = original(*args, **kwargs)
            response.json.return_value["seriess"][0]["units"] = "other"
            return response
        session.get.side_effect = wrong_unit
        with self.assertRaises(ValueError):
            self.run_history(session)
        self.assert_failed("extraction", 1)
        path = self.root / self.connection.execute("SELECT storage_path FROM ops.raw_captures").fetchone()[0]
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["payload"]["units"], "other")

    def test_missing_calendar_stops_before_observation_requests(self):
        session = historical_session()
        with self.assertRaisesRegex(ValueError, "2027"):
            self.run_history(session, start=date(2027, 1, 1), end=date(2027, 1, 1), as_of=date(2027, 2, 1))
        self.assertEqual(session.get.call_count, 4)
        self.assert_failed("extraction", 4)

    def test_truncated_fred_page_is_archived_and_blocks_further_requests(self):
        session = historical_session()
        original = session.get.side_effect
        def truncated(url, **kwargs):
            response = original(url, **kwargs)
            if url.endswith("series/observations"):
                response.json.return_value["count"] += 1
            return response
        session.get.side_effect = truncated
        with self.assertRaises(ValueError):
            self.run_history(session)
        self.assertEqual(session.get.call_count, 5)
        self.assert_failed("extraction", 5)

    def test_incomplete_fix_has_a_consolidated_profile_and_durable_failed_coverage(self):
        session = historical_session()
        original = session.get.side_effect
        def missing_fix(url, **kwargs):
            response = original(url, **kwargs)
            if "/datos/" in url:
                response.json.return_value["bmx"]["series"][0]["datos"].pop(0)
            return response
        session.get.side_effect = missing_fix
        with self.assertRaises(ValueError):
            self.run_history(session)
        self.assert_failed("quality", 8)
        path = next(self.root.glob("historical/*/historical_profile.json"))
        self.assertTrue(json.loads(path.read_text(encoding="utf-8"))["has_issues"])
        self.assertEqual(self.connection.execute("SELECT status FROM ops.dq_results WHERE rule_code = 'DQ-09'").fetchone()[0], "failed")

    def test_publication_failure_keeps_its_actual_stage_instead_of_reclosing_as_extraction(self):
        with patch("grain_pipeline.orchestration.publication.complete_publication", side_effect=RuntimeError("fixture")):
            with self.assertRaises(RuntimeError):
                self.run_history(historical_session())
        self.assert_failed("publication", 8)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM ops.dq_results WHERE rule_code = 'CTL-03' AND status = 'failed'").fetchone()[0], 1)

    def test_cli_loads_only_fixture_configuration_and_runs_the_real_historical_path(self):
        session = historical_session()
        env_file = self.root.parent / "fixture.env"
        env_file.write_text(f"FRED_API_KEY=fixture-fred-key\nBANXICO_TOKEN=fixture-banxico-token\nDATABASE_URL={self.database_url}\n", encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True), patch("grain_pipeline.orchestration.historical.requests.Session", return_value=session):
            with patch("grain_pipeline.orchestration.historical.logging.basicConfig"), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = main(["--start-month", "2026-09", "--end-month", "2026-09", "--env-file", str(env_file), "--bronze-root", str(self.root)])
        self.assertEqual(code, 0)
        self.assertEqual(self.connection.execute("SELECT status FROM ops.runs").fetchone()[0], "succeeded")
