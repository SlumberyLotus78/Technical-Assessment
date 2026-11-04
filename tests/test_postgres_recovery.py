"""Recuperación y reproceso sobre bases desechables; ningún dato del proyecto se utiliza."""

from contextlib import redirect_stdout
from datetime import date
from decimal import Decimal
import io
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
from uuid import UUID

import psycopg

from grain_pipeline.orchestration.historical import run_historical
from grain_pipeline.orchestration.recovery import main as recovery_main, recover_run
from grain_pipeline.orchestration.reprocess import run_reprocess
from grain_pipeline.persistence.captures import register_capture
from grain_pipeline.persistence.catalog import prepare_catalog
from grain_pipeline.persistence.locking import acquire_product_lock
from grain_pipeline.persistence.runs import begin_run, fail_run, set_run_stage
from grain_pipeline.persistence.schema import apply_schema
from grain_pipeline.persistence.watermarks import complete_publication
from tests.historical_fixtures import CREDENTIALS, historical_session
from tests.postgres_support import PostgresTestCase
from tests.publication_fixtures import publication_capture_files


JULY, AUGUST, SEPTEMBER, TODAY = date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1), date(2026, 11, 3)


class PostgresRecoveryTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        apply_schema(self.connection)
        prepare_catalog(self.connection)
        self.connection.commit()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "bronze"
        self.root.mkdir()

    def attempt(self, *, start=JULY, end=SEPTEMBER, count=8, failed=False, overrides=None):
        run_id = begin_run(self.connection, "historical", start, end)
        paths = publication_capture_files(self.root, start, end, overrides=overrides) if start is not None else []
        for path in paths[:count]:
            register_capture(self.connection, run_id, path, self.root)
        if start is not None:
            set_run_stage(self.connection, run_id, "quality")
        if failed:
            fail_run(self.connection, run_id, "quality", ValueError("fixture-private-error"))
        self.connection.commit()
        return run_id, paths

    def seed(self, start=JULY):
        return run_historical(self.connection, historical_session(), CREDENTIALS, self.root, start, SEPTEMBER, as_of=TODAY)

    def snapshot(self):
        rows = {table: self.connection.execute(f"SELECT * FROM {table} ORDER BY 1, 2, 3").fetchall()
                for table in ("core.observations", "mart.fx_monthly", "mart.grain_reference_monthly", "ops.watermarks")}
        self.connection.commit()
        return rows

    def test_orphan_is_closed_and_a_new_attempt_reuses_original_capture_owners(self):
        old_id, _ = self.attempt()
        result = recover_run(self.connection, old_id, self.root, as_of=TODAY)
        self.assertEqual(result["action"], "recovered")
        self.assertNotEqual(result["run_id"], str(old_id))
        self.assertEqual(self.connection.execute("SELECT status, stage FROM ops.runs WHERE run_id = %s", (old_id,)).fetchone(), ("failed", "quality"))
        self.assertEqual(self.connection.execute("SELECT DISTINCT run_id FROM ops.raw_captures").fetchall(), [(old_id,)])
        self.assertEqual(self.connection.execute("SELECT count(*) FROM mart.grain_reference_monthly").fetchone()[0], 9)
        self.connection.commit()
        before = self.snapshot()
        again = recover_run(self.connection, old_id, self.root, as_of=TODAY)
        self.assertEqual(again["action"], "already_completed")
        self.assertEqual(again["run_id"], result["run_id"])
        self.assertEqual(self.snapshot(), before)

    def test_failed_attempt_keeps_its_original_failure_when_recovered(self):
        old_id, _ = self.attempt(failed=True)
        old = self.connection.execute("SELECT finished_at, error_summary FROM ops.runs WHERE run_id = %s", (old_id,)).fetchone()
        self.connection.commit()
        result = recover_run(self.connection, old_id, self.root, as_of=TODAY)
        self.assertEqual(result["action"], "recovered")
        self.assertEqual(self.connection.execute("SELECT finished_at, error_summary FROM ops.runs WHERE run_id = %s", (old_id,)).fetchone(), old)

    def test_partial_and_unplanned_orphans_close_without_fabricating_inputs(self):
        partial, _ = self.attempt(count=7)
        result = recover_run(self.connection, partial, self.root, as_of=TODAY)
        self.assertEqual(result["reason"], "incomplete_capture_set")
        self.assertTrue(result["retry"].startswith("historical "))
        unplanned, _ = self.attempt(start=None, end=None, count=0)
        result = recover_run(self.connection, unplanned, self.root, as_of=TODAY)
        self.assertEqual(result["reason"], "unplanned_window")
        self.assertEqual(self.connection.execute("SELECT DISTINCT status FROM ops.runs").fetchall(), [("failed",)])
        self.assertFalse(self.snapshot()["ops.watermarks"])

    def test_active_product_lock_prevents_closing_another_process(self):
        old_id, _ = self.attempt()
        with psycopg.connect(self.database_url) as other:
            self.assertTrue(acquire_product_lock(other))
            other.commit()
            with self.assertRaises(RuntimeError):
                recover_run(self.connection, old_id, self.root, as_of=TODAY)
            self.assertEqual(self.connection.execute("SELECT status FROM ops.runs WHERE run_id = %s", (old_id,)).fetchone()[0], "running")

    def test_later_publication_blocks_replaying_old_corrections(self):
        self.seed()
        old_id, _ = self.attempt(start=AUGUST, end=AUGUST, failed=True, overrides={("PMAIZMTUSDM", AUGUST): "150"})
        run_reprocess(self.connection, historical_session(overrides={("PMAIZMTUSDM", AUGUST): "200"}),
                      CREDENTIALS, self.root, AUGUST, AUGUST, as_of=TODAY)
        before = self.snapshot()
        result = recover_run(self.connection, old_id, self.root, as_of=TODAY)
        self.assertEqual(result["reason"], "newer_publication")
        self.assertTrue(result["retry"].startswith("reprocess "))
        self.assertEqual(self.snapshot(), before)

    def test_tampered_or_missing_capture_cannot_publish_and_closure_is_durable(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                old_id, paths = self.attempt()
                if missing:
                    paths[-1].unlink()
                else:
                    paths[-1].write_text(paths[-1].read_text(encoding="utf-8") + " ", encoding="utf-8")
                with self.assertRaises((ValueError, OSError)):
                    recover_run(self.connection, old_id, self.root, as_of=TODAY)
                self.assertEqual(self.connection.execute("SELECT status FROM ops.runs WHERE run_id = %s", (old_id,)).fetchone()[0], "failed")
                self.assertEqual(self.connection.execute("SELECT count(*) FROM ops.runs WHERE status = 'running'").fetchone()[0], 0)
                self.assertFalse(self.snapshot()["ops.watermarks"])

    def test_failure_after_watermark_rolls_back_and_recovery_child_can_resume(self):
        old_id, _ = self.attempt()
        before = self.snapshot()
        def fail_after_finalizer(*args, **kwargs):
            complete_publication(*args, **kwargs)
            raise RuntimeError("injected-after-watermark")
        with patch("grain_pipeline.orchestration.publication.complete_publication", side_effect=fail_after_finalizer):
            with self.assertRaises(RuntimeError):
                recover_run(self.connection, old_id, self.root, as_of=TODAY)
        self.assertEqual(self.snapshot(), before)
        child = self.connection.execute("SELECT run_id FROM ops.runs WHERE run_id <> %s", (old_id,)).fetchone()[0]
        self.connection.commit()
        result = recover_run(self.connection, child, self.root, as_of=TODAY)
        self.assertEqual(result["action"], "recovered")
        self.assertEqual(self.connection.execute("SELECT count(*) FROM ops.raw_captures").fetchone()[0], 8)

    def test_recovery_cli_needs_only_database_configuration(self):
        old_id, _ = self.attempt()
        env_file = self.root.parent / "fixture.env"
        env_file.write_text("DATABASE_URL=" + self.database_url, encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(recovery_main(["--run-id", str(old_id), "--env-file", str(env_file), "--bronze-root", str(self.root)]), 0)
        self.assertIn("recovered", output.getvalue())

    def test_reprocessing_old_month_recalculates_later_mom_and_yoy_without_extending_watermark(self):
        old_month = date(2025, 7, 1)
        self.seed(start=old_month)
        before = self.snapshot()["ops.watermarks"][0]
        result = run_reprocess(self.connection, historical_session(overrides={("PMAIZMTUSDM", old_month): "125"}),
                               CREDENTIALS, self.root, old_month, old_month, as_of=TODAY)
        self.assertEqual(result["silver"]["written"], 1)
        self.assertEqual(result["gold"]["grain_reference_monthly"]["written"], 3)
        after = self.snapshot()["ops.watermarks"][0]
        self.assertEqual(after[1:4], before[1:4])  # Inicio, fin y ejecución histórica inicial.
        self.assertEqual(after[4], UUID(result["run_id"]))

    def test_unchanged_reprocess_preserves_all_fact_audit_fields(self):
        self.seed()
        before = self.snapshot()
        result = run_reprocess(self.connection, historical_session(), CREDENTIALS, self.root, JULY, AUGUST, as_of=TODAY)
        self.assertEqual(result["silver"]["written"], 0)
        after = self.snapshot()
        for table in ("core.observations", "mart.fx_monthly", "mart.grain_reference_monthly"):
            self.assertEqual(after[table], before[table])

    def test_reprocess_rejects_initialization_and_outside_period_before_http(self):
        session = historical_session()
        with self.assertRaises(ValueError):
            run_reprocess(self.connection, session, CREDENTIALS, self.root, JULY, SEPTEMBER, as_of=TODAY)
        session.get.assert_not_called()
        self.seed()
        before = self.snapshot()
        for start, end in ((date(2026, 6, 1), JULY), (SEPTEMBER, date(2026, 10, 1))):
            session = historical_session()
            with self.assertRaises(ValueError):
                run_reprocess(self.connection, session, CREDENTIALS, self.root, start, end, as_of=TODAY)
            session.get.assert_not_called()
            self.assertEqual(self.snapshot(), before)

    def test_bad_reprocessing_inputs_preserve_previous_product(self):
        self.seed()
        before = self.snapshot()
        with self.assertRaises(ValueError):
            run_reprocess(self.connection, historical_session(overrides={("PMAIZMTUSDM", JULY): "0"}),
                          CREDENTIALS, self.root, JULY, JULY, as_of=TODAY)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.connection.execute("SELECT status FROM ops.runs ORDER BY started_at DESC LIMIT 1").fetchone()[0], "failed")
