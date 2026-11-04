"""Incremental con PostgreSQL real desechable y HTTP simulado, sin usar el .env del proyecto."""

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

from grain_pipeline.orchestration.historical import run_historical
from grain_pipeline.orchestration.incremental import main, run_incremental
from grain_pipeline.persistence.catalog import prepare_catalog
from grain_pipeline.persistence.locking import acquire_product_lock
from grain_pipeline.persistence.runs import begin_run, set_run_period
from grain_pipeline.persistence.schema import apply_schema
from grain_pipeline.persistence.watermarks import complete_publication, complete_skipped_incremental, read_watermark
from grain_pipeline.sources.catalog import SERIES
from tests.historical_fixtures import CREDENTIALS, historical_session
from tests.postgres_support import PostgresTestCase


MONTH, AS_OF = date(2026, 9, 1), date(2026, 11, 3)
JULY = date(2026, 7, 1)


class PostgresIncrementalTests(PostgresTestCase):
    """Verifica avance, revisiones, omisiones y fallos sobre una base propia por caso."""

    def setUp(self):
        super().setUp()
        apply_schema(self.connection)
        prepare_catalog(self.connection)
        self.connection.commit()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "bronze"

    def seed_history(self, start=JULY, end=MONTH, *, session=None, as_of=AS_OF):
        return run_historical(self.connection, historical_session() if session is None else session,
                              CREDENTIALS, self.root, start, end, as_of=as_of)

    def update(self, session=None, *, review_months=3, as_of=AS_OF, end_month=None):
        return run_incremental(self.connection, historical_session() if session is None else session,
                               CREDENTIALS, self.root, as_of=as_of, review_months=review_months, end_month=end_month)

    def snapshot(self):
        data = {table: self.connection.execute(f"SELECT * FROM {table} ORDER BY 1, 2, 3").fetchall()
                for table in ("core.observations", "mart.fx_monthly", "mart.grain_reference_monthly", "ops.watermarks")}
        self.connection.commit()
        return data

    def test_missing_history_is_failed_without_api_calls_or_invoking_historical(self):
        session = historical_session()
        with patch("grain_pipeline.orchestration.historical.run_historical") as historical:
            with self.assertRaises(ValueError):
                self.update(session)
            historical.assert_not_called()
        session.get.assert_not_called()
        self.assertEqual(self.connection.execute("SELECT load_type, status, stage, start_month FROM ops.runs").fetchone(),
                         ("incremental", "failed", "planning", None))
        self.assertEqual(self.connection.execute("SELECT count(*) FROM ops.watermarks").fetchone()[0], 0)

    def test_review_without_new_months_confirms_checks_and_preserves_fact_audit(self):
        initial = self.seed_history()
        before = self.snapshot()
        session = historical_session()
        with patch("grain_pipeline.orchestration.historical.run_historical") as historical:
            result = self.update(session)
            historical.assert_not_called()
        self.assertEqual(session.get.call_count, 8)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["request_start_month"], "2026-07-01")
        self.assertEqual(result["silver"]["written"], 0)
        self.assertEqual(result["gold"]["grain_reference_monthly"]["written"], 0)
        after = self.snapshot()
        for table in ("core.observations", "mart.fx_monthly", "mart.grain_reference_monthly"):
            self.assertEqual(after[table], before[table])
        self.assertEqual(self.connection.execute("SELECT initial_run_id::text, last_run_id::text FROM ops.watermarks").fetchone(),
                         (initial["run_id"], result["run_id"]))
        path = self.root / result["bronze_directory"] / "incoming_profile.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["start_month"], "2026-07-01")

    def test_full_original_history_fetches_only_recent_window_to_add_october(self):
        self.seed_history(start=date(2009, 1, 1))
        session = historical_session(latest_month=date(2026, 10, 1))
        result = self.update(session)
        self.assertEqual(session.get.call_count, 8)
        self.assertEqual(result["request_start_month"], "2026-07-01")
        self.assertEqual(result["request_end_month"], "2026-10-01")
        self.assertEqual(result["silver"]["written"], 25)
        self.assertEqual(result["watermark_after"], "2026-10-01")
        self.assertEqual(self.connection.execute("SELECT count(*) FROM core.observations").fetchone()[0], 5127)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM mart.fx_monthly").fetchone()[0], 214)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM mart.grain_reference_monthly").fetchone()[0], 642)

    def test_grain_revision_updates_its_reference_and_later_mom(self):
        self.seed_history()
        result = self.update(historical_session(overrides={(SERIES[0]["code"], date(2026, 8, 1)): "110"}))
        self.assertEqual(result["silver"]["written"], 1)
        self.assertEqual(result["gold"]["fx_monthly"]["written"], 0)
        self.assertEqual(result["gold"]["grain_reference_monthly"]["written"], 2)
        rows = self.connection.execute(
            "SELECT month, reference_mxn_t, mom_change_pct FROM mart.grain_reference_monthly WHERE series_code = %s ORDER BY month",
            (SERIES[0]["code"],)).fetchall()
        self.assertEqual(rows[1][1:], (Decimal(2200), Decimal(10)))
        self.assertTrue(rows[2][2] < 0)

    def test_fix_revision_changes_the_monthly_average_and_all_three_references(self):
        self.seed_history()
        result = self.update(historical_session(overrides={("SF43718", MONTH): "21"}))
        self.assertEqual(result["silver"]["written"], 1)
        self.assertEqual(result["gold"]["fx_monthly"]["written"], 1)
        self.assertEqual(result["gold"]["grain_reference_monthly"]["written"], 3)
        self.assertTrue(self.connection.execute("SELECT average_fix FROM mart.fx_monthly WHERE month = %s", (MONTH,)).fetchone()[0] > 20)

    def test_no_new_months_with_review_disabled_skips_without_touching_watermark(self):
        self.seed_history()
        before = self.snapshot()
        session = historical_session()
        with patch("grain_pipeline.orchestration.incremental.collect_observation_windows") as observations:
            with patch("grain_pipeline.orchestration.incremental.publish_registered_captures") as publisher:
                result = self.update(session, review_months=0)
                observations.assert_not_called()
                publisher.assert_not_called()
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(session.get.call_count, 4)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.connection.execute(
            "SELECT status, stage, start_month, end_month FROM ops.runs WHERE run_id::text = %s", (result["run_id"],)).fetchone(),
            ("skipped", "planning", None, None))
        directory = self.root / result["bronze_directory"]
        plan = json.loads((directory / "query_plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["observation_requests"], 0)
        self.assertFalse((directory / "incoming_profile.json").exists())
        self.assertTrue((directory / "run_result.json").is_file())

    def test_skip_cannot_hide_inconsistent_gold_and_does_not_repair_it_silently(self):
        self.seed_history()
        self.connection.execute("UPDATE mart.grain_reference_monthly SET reference_mxn_t = reference_mxn_t + 1")
        self.connection.commit()
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.update(review_months=0)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.connection.execute("SELECT status, stage FROM ops.runs ORDER BY started_at DESC LIMIT 1").fetchone(),
                         ("failed", "planning"))

    def test_catch_up_with_zero_review_includes_all_new_months(self):
        self.seed_history(start=MONTH)
        session = historical_session(latest_month=date(2026, 12, 1), banxico_last=date(2026, 12, 31))
        result = self.update(session, review_months=0, as_of=date(2027, 1, 3))
        self.assertEqual(result["request_start_month"], "2026-10-01")
        self.assertEqual(result["request_end_month"], "2026-12-01")
        self.assertEqual(self.connection.execute("SELECT count(*) FROM mart.fx_monthly").fetchone()[0], 4)
        self.assertEqual(self.connection.execute("SELECT published_through_month FROM ops.watermarks").fetchone()[0], date(2026, 12, 1))

    def test_year_boundary_uses_two_windows_without_duplicate_dates(self):
        self.seed_history(start=date(2025, 11, 1), end=date(2026, 1, 1))
        session = historical_session(latest_month=date(2026, 2, 1))
        result = self.update(session, as_of=date(2026, 3, 3))
        self.assertEqual(session.get.call_count, 12)
        self.assertEqual(result["request_start_month"], "2025-11-01")
        self.assertEqual(result["watermark_after"], "2026-02-01")
        self.assertEqual(self.connection.execute("SELECT count(*) FROM mart.fx_monthly").fetchone()[0], 4)

    def test_source_regression_fails_before_observations_and_preserves_publication(self):
        self.seed_history()
        before = self.snapshot()
        sources = (historical_session(latest_month=date(2026, 8, 1)),
                   historical_session(banxico_last=date(2026, 9, 29)))
        for session in sources:
            with self.assertRaises(ValueError):
                self.update(session, review_months=0)
            self.assertEqual(session.get.call_count, 4)
            self.assertEqual(self.snapshot(), before)

    def test_incomplete_declared_fix_or_unreviewed_new_year_stops_before_observations(self):
        self.seed_history()
        before = self.snapshot()
        session = historical_session(latest_month=date(2026, 10, 1), banxico_last=date(2026, 10, 29))
        with self.assertRaises(ValueError):
            self.update(session)
        self.assertEqual(session.get.call_count, 4)
        self.assertEqual(self.snapshot(), before)
        session = historical_session(latest_month=date(2027, 1, 1), banxico_last=date(2027, 2, 3))
        with self.assertRaisesRegex(ValueError, "2027"):
            self.update(session, as_of=date(2027, 2, 3))
        self.assertEqual(session.get.call_count, 4)
        self.assertEqual(self.snapshot(), before)

    def test_failure_after_watermark_update_rolls_back_increment_and_keeps_new_captures(self):
        self.seed_history()
        before = self.snapshot()
        def fail_after_finalizer(*args, **kwargs):
            complete_publication(*args, **kwargs)
            raise RuntimeError("fixture-private")
        with patch("grain_pipeline.orchestration.publication.complete_publication", side_effect=fail_after_finalizer):
            with self.assertRaises(RuntimeError):
                self.update(historical_session(latest_month=date(2026, 10, 1)))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM ops.raw_captures").fetchone()[0], 16)
        self.assertEqual(self.connection.execute("SELECT status, stage, error_summary FROM ops.runs ORDER BY started_at DESC LIMIT 1").fetchone(),
                         ("failed", "publication", "RuntimeError"))

    def test_network_uses_idle_sql_connection_and_holds_the_product_lock(self):
        self.seed_history()
        session = historical_session()
        original = session.get.side_effect
        with psycopg.connect(self.database_url) as other:
            def inspect_request(*args, **kwargs):
                self.assertEqual(self.connection.info.transaction_status, TransactionStatus.IDLE)
                self.assertFalse(acquire_product_lock(other))
                other.commit()
                return original(*args, **kwargs)
            session.get.side_effect = inspect_request
            self.update(session)

    def test_skipped_finalizer_and_period_assignment_reject_incompatible_attempts(self):
        self.seed_history()
        previous = read_watermark(self.connection)
        run_id = begin_run(self.connection, "historical", MONTH, MONTH)
        with self.assertRaises(ValueError):
            complete_skipped_incremental(self.connection, run_id, previous, self.root, as_of=AS_OF)
        run_id = begin_run(self.connection, "incremental")
        set_run_period(self.connection, run_id, MONTH, MONTH)
        with self.assertRaises(ValueError):
            set_run_period(self.connection, run_id, MONTH, MONTH)
        with self.assertRaises(ValueError):
            complete_skipped_incremental(self.connection, run_id, previous, self.root, as_of=AS_OF)
        self.connection.rollback()

    def test_cli_uses_fixture_configuration_and_never_initializes_history(self):
        self.seed_history()
        session = historical_session()
        env_file = self.root.parent / "fixture.env"
        env_file.write_text(f"FRED_API_KEY=fixture-fred-key\nBANXICO_TOKEN=fixture-banxico-token\nDATABASE_URL={self.database_url}\n", encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True), patch("grain_pipeline.orchestration.incremental.requests.Session", return_value=session):
            with patch("grain_pipeline.orchestration.incremental.logging.basicConfig"), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--env-file", str(env_file), "--bronze-root", str(self.root)]), 0)
        self.assertEqual(self.connection.execute("SELECT load_type, status FROM ops.runs ORDER BY started_at DESC LIMIT 1").fetchone(),
                         ("incremental", "succeeded"))
