"""Publicación real con capturas ficticias y bases PostgreSQL desechables."""

from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import psycopg

from grain_pipeline.orchestration.locking import product_publication_lock
from grain_pipeline.orchestration.publication import publish_registered_captures
from grain_pipeline.persistence.captures import register_capture
from grain_pipeline.persistence.catalog import prepare_catalog
from grain_pipeline.persistence.gold import save_monthly_gold
from grain_pipeline.persistence.observations import save_capture_observations
from grain_pipeline.persistence.runs import begin_run, set_run_stage
from grain_pipeline.persistence.schema import apply_schema
from grain_pipeline.persistence.watermarks import complete_publication
from grain_pipeline.sources.catalog import SERIES
from tests.postgres_support import PostgresTestCase
from tests.publication_fixtures import publication_capture_files


MONTH, AS_OF = date(2026, 9, 1), date(2026, 11, 3)


class PostgresPublicationTests(PostgresTestCase):
    """Cada caso obtiene su propia base; nunca se utiliza DATABASE_URL del proyecto."""

    def setUp(self):
        super().setUp()
        apply_schema(self.connection)
        prepare_catalog(self.connection)
        self.connection.commit()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def attempt(self, mode="historical", start=MONTH, end=MONTH, *, overrides=None, edit=None):
        """Confirma intento y capturas como hará el coordinador de extracción."""
        paths = publication_capture_files(self.root, start, end, overrides=overrides)
        if edit is not None:
            edit(paths)
        run_id = begin_run(self.connection, mode, start, end)
        set_run_stage(self.connection, run_id, "extraction")
        ids = [register_capture(self.connection, run_id, path, self.root) for path in paths]
        self.connection.commit()
        return run_id, ids, paths

    def publish(self, attempt, *, as_of=AS_OF):
        return publish_registered_captures(self.connection, attempt[0], attempt[1], self.root, as_of=as_of)

    def snapshot(self):
        """Incluye auditoría para comprobar que una repetición no modifica filas."""
        data = {table: self.connection.execute(f"SELECT * FROM {table} ORDER BY 1, 2, 3").fetchall()
                for table in ("core.observations", "mart.fx_monthly", "mart.grain_reference_monthly")}
        self.connection.commit()
        return data

    def assert_failed_without_facts(self, run_id, stage):
        status = self.connection.execute("SELECT status, stage FROM ops.runs WHERE run_id = %s", (run_id,)).fetchone()
        self.assertEqual(status, ("failed", stage))
        for table in ("core.observations", "mart.fx_monthly", "mart.grain_reference_monthly", "ops.watermarks"):
            self.assertEqual(self.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM ops.raw_captures").fetchone()[0], 8)
        self.connection.commit()

    def test_initial_history_publishes_all_layers_and_success_together(self):
        attempt = self.attempt()
        metrics = self.publish(attempt)
        self.assertEqual(metrics["silver"], {"received": 24, "written": 24, "unchanged": 0})
        self.assertEqual(metrics["gold"]["fx_monthly"]["written"], 1)
        self.assertEqual(metrics["gold"]["grain_reference_monthly"]["written"], 3)
        with psycopg.connect(self.database_url, autocommit=True) as observer:
            self.assertEqual(observer.execute("SELECT status, stage FROM ops.runs WHERE run_id = %s", (attempt[0],)).fetchone(),
                             ("succeeded", "publication"))
            self.assertEqual(observer.execute(
                "SELECT start_month, published_through_month, initial_run_id, last_run_id FROM ops.watermarks").fetchone(),
                (MONTH, MONTH, attempt[0], attempt[0]))
            self.assertEqual(observer.execute("SELECT average_fix, observed_days, expected_days FROM mart.fx_monthly").fetchone(),
                             (Decimal(20), 21, 21))
            self.assertEqual(observer.execute("SELECT count(*) FROM ops.dq_results WHERE status <> 'passed'").fetchone()[0], 0)

    def test_unchanged_repeat_keeps_silver_and_gold_audit_fields(self):
        first = self.attempt()
        self.publish(first)
        before = self.snapshot()
        second = self.attempt()
        metrics = self.publish(second)
        self.assertEqual(metrics["silver"]["written"], 0)
        self.assertEqual(metrics["gold"]["fx_monthly"]["written"], 0)
        self.assertEqual(metrics["gold"]["grain_reference_monthly"]["written"], 0)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.connection.execute("SELECT initial_run_id, last_run_id FROM ops.watermarks").fetchone(),
                         (first[0], second[0]))

    def test_revision_recalculates_prior_context_and_later_mom_without_retreating_watermark(self):
        july, august = date(2026, 7, 1), date(2026, 8, 1)
        first = self.attempt(start=july)
        self.publish(first)
        revision = self.attempt(start=august, end=august, overrides={(SERIES[0]["code"], august): "110"})
        metrics = self.publish(revision)
        self.assertEqual(metrics["silver"]["written"], 1)
        self.assertEqual(metrics["gold"]["fx_monthly"]["written"], 0)
        self.assertEqual(metrics["gold"]["grain_reference_monthly"]["written"], 2)
        rows = self.connection.execute(
            """SELECT month, reference_mxn_t, mom_change_pct, source_run_id FROM mart.grain_reference_monthly
               WHERE series_code = %s ORDER BY month""", (SERIES[0]["code"],)).fetchall()
        self.assertEqual(rows[1][1:3], (Decimal(2200), Decimal(10)))
        self.assertEqual(rows[2][1], Decimal(2000))
        self.assertTrue(rows[2][2] < 0)
        self.assertEqual(rows[2][3], revision[0])
        self.assertEqual(self.connection.execute(
            "SELECT start_month, published_through_month, initial_run_id FROM ops.watermarks").fetchone(),
            (july, MONTH, first[0]))

    def test_incremental_requires_baseline_and_then_extends_continuously(self):
        first = self.attempt()
        self.publish(first)
        october = date(2026, 10, 1)
        incremental = self.attempt("incremental", october, october)
        self.publish(incremental)
        self.assertEqual(self.connection.execute(
            "SELECT start_month, published_through_month, initial_run_id, last_run_id FROM ops.watermarks").fetchone(),
            (MONTH, october, first[0], incremental[0]))
        self.assertEqual(self.connection.execute("SELECT count(*) FROM mart.fx_monthly").fetchone()[0], 2)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM mart.grain_reference_monthly").fetchone()[0], 6)

    def test_incremental_without_history_fails_and_preserves_attempt_captures(self):
        attempt = self.attempt("incremental")
        with self.assertRaises(ValueError):
            self.publish(attempt)
        self.assert_failed_without_facts(attempt[0], "planning")
        self.assertEqual(self.connection.execute("SELECT status FROM ops.dq_results WHERE rule_code = 'CTL-01'").fetchone()[0], "failed")

    def test_gap_or_earlier_extension_keeps_the_existing_publication(self):
        first = self.attempt()
        self.publish(first)
        before = self.snapshot()
        november = date(2026, 11, 1)
        attempt = self.attempt("incremental", november, november)
        with self.assertRaises(ValueError):
            self.publish(attempt, as_of=date(2026, 12, 1))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.connection.execute("SELECT published_through_month FROM ops.watermarks").fetchone()[0], MONTH)

    def test_missing_fix_preserves_detailed_failed_dq_and_never_publishes(self):
        def remove_fix(paths):
            path = next(path for path in paths if path.name == "banxico_SF43718_observations.json")
            body = json.loads(path.read_text(encoding="utf-8"))
            body["payload"]["bmx"]["series"][0]["datos"].pop(0)
            path.write_text(json.dumps(body), encoding="utf-8")

        attempt = self.attempt(edit=remove_fix)
        with self.assertRaises(ValueError):
            self.publish(attempt)
        self.assert_failed_without_facts(attempt[0], "quality")
        row = self.connection.execute("SELECT status, details FROM ops.dq_results WHERE rule_code = 'DQ-09'").fetchone()
        self.assertEqual(row[0], "failed")
        self.assertEqual(row[1]["missing_dates"], ["2026-09-01"])

    def test_invalid_metadata_preserves_its_failed_source_check(self):
        def change_unit(paths):
            path = next(path for path in paths if path.name == "fred_PMAIZMTUSDM_metadata.json")
            body = json.loads(path.read_text(encoding="utf-8"))
            body["payload"]["units"] = "other"
            path.write_text(json.dumps(body), encoding="utf-8")

        attempt = self.attempt(edit=change_unit)
        with self.assertRaises(ValueError):
            self.publish(attempt)
        self.assert_failed_without_facts(attempt[0], "quality")
        self.assertEqual(self.connection.execute(
            "SELECT count(*) FROM ops.dq_results WHERE rule_code = 'SRC-02' AND status = 'failed'").fetchone()[0], 1)

    def test_tampered_registered_capture_blocks_before_silver(self):
        attempt = self.attempt()
        attempt[2][0].write_text('{}', encoding="utf-8")
        with self.assertRaises(ValueError):
            self.publish(attempt)
        self.assert_failed_without_facts(attempt[0], "quality")
        self.assertEqual(self.connection.execute(
            "SELECT count(*) FROM ops.dq_results WHERE rule_code = 'LIN-01' AND status = 'failed'").fetchone()[0], 1)

    def test_gold_failure_rolls_back_silver_and_keeps_dq_without_private_error(self):
        attempt = self.attempt()
        with patch("grain_pipeline.orchestration.publication.save_monthly_gold", side_effect=RuntimeError("fixture-private-secret")):
            with self.assertRaises(RuntimeError):
                self.publish(attempt)
        self.assert_failed_without_facts(attempt[0], "gold")
        self.assertTrue(self.connection.execute("SELECT count(*) FROM ops.dq_results WHERE status = 'passed'").fetchone()[0] > 0)
        self.assertEqual(self.connection.execute("SELECT error_summary FROM ops.runs WHERE run_id = %s", (attempt[0],)).fetchone()[0],
                         "RuntimeError")
        self.connection.commit()
        # Una ejecución posterior puede publicar: el fallo liberó el bloqueo.
        self.publish(self.attempt())

    def test_failure_after_gold_reverts_all_product_tables(self):
        attempt = self.attempt()
        with patch("grain_pipeline.orchestration.publication.complete_publication", side_effect=RuntimeError("fixture")):
            with self.assertRaises(RuntimeError):
                self.publish(attempt)
        self.assert_failed_without_facts(attempt[0], "publication")

    def test_failure_after_watermark_and_success_updates_reverts_them_too(self):
        attempt = self.attempt()

        def fail_after_finalizer(*args, **kwargs):
            complete_publication(*args, **kwargs)
            raise RuntimeError("fixture after watermark")

        with patch("grain_pipeline.orchestration.publication.complete_publication", side_effect=fail_after_finalizer):
            with self.assertRaises(RuntimeError):
                self.publish(attempt)
        self.assert_failed_without_facts(attempt[0], "publication")

    def test_other_sessions_see_the_previous_publication_until_commit(self):
        first = self.attempt()
        self.publish(first)
        october = date(2026, 10, 1)
        incremental = self.attempt("incremental", october, october)

        def observe_before_commit(*args, **kwargs):
            complete_publication(*args, **kwargs)
            with psycopg.connect(self.database_url, autocommit=True) as observer:
                self.assertEqual(observer.execute("SELECT count(*) FROM core.observations").fetchone()[0], 24)
                self.assertEqual(observer.execute("SELECT count(*) FROM mart.fx_monthly").fetchone()[0], 1)
                self.assertEqual(observer.execute("SELECT count(*) FROM mart.grain_reference_monthly").fetchone()[0], 3)
                self.assertEqual(observer.execute("SELECT published_through_month, last_run_id FROM ops.watermarks").fetchone(),
                                 (MONTH, first[0]))
                self.assertEqual(observer.execute("SELECT status FROM ops.runs WHERE run_id = %s", (incremental[0],)).fetchone()[0],
                                 "running")

        with patch("grain_pipeline.orchestration.publication.complete_publication", side_effect=observe_before_commit):
            self.publish(incremental)
        self.assertEqual(self.connection.execute("SELECT published_through_month FROM ops.watermarks").fetchone()[0], october)

    def test_duplicate_observations_between_captures_have_a_global_failed_check(self):
        attempt = self.attempt()
        original = next(path for path in attempt[2] if path.name == "fred_PMAIZMTUSDM_observations.json")
        duplicate = original.with_name("second_fragment.json")
        duplicate.write_bytes(original.read_bytes())
        extra_id = register_capture(self.connection, attempt[0], duplicate, self.root)
        self.connection.commit()
        attempt[1].append(extra_id)
        with self.assertRaises(ValueError):
            self.publish(attempt)
        row = self.connection.execute(
            """SELECT status, details FROM ops.dq_results
               WHERE rule_code = 'DQ-06' AND details->>'scope' = 'combined_inputs'""").fetchone()
        self.assertEqual(row[0], "failed")
        self.assertEqual(row[1]["duplicates"][0]["count"], 2)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM core.observations").fetchone()[0], 0)

    def test_finalizer_cannot_succeed_from_stage_alone_without_gold(self):
        attempt = self.attempt()
        set_run_stage(self.connection, attempt[0], "publication")
        with self.assertRaises(ValueError):
            complete_publication(self.connection, attempt[0], None,
                                 {"start_month": MONTH, "end_month": MONTH}, self.root, as_of=AS_OF)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM ops.watermarks").fetchone()[0], 0)
        self.assertEqual(self.connection.execute("SELECT status FROM ops.runs WHERE run_id = %s", (attempt[0],)).fetchone()[0], "running")
        self.connection.rollback()

    def test_wrong_gold_value_with_correct_counts_is_detected_before_commit(self):
        attempt = self.attempt()

        def corrupt_after_save(*args, **kwargs):
            result = save_monthly_gold(*args, **kwargs)
            self.connection.execute("UPDATE mart.grain_reference_monthly SET reference_mxn_t = reference_mxn_t + 1")
            return result

        with patch("grain_pipeline.orchestration.publication.save_monthly_gold", side_effect=corrupt_after_save):
            with self.assertRaises(ValueError):
                self.publish(attempt)
        self.assert_failed_without_facts(attempt[0], "gold")

    def test_silver_values_must_match_bronze_before_reusing_a_baseline(self):
        self.publish(self.attempt())
        self.connection.execute("UPDATE core.observations SET value = 999 WHERE series_code = %s", (SERIES[0]["code"],))
        self.connection.commit()
        before = self.snapshot()
        attempt = self.attempt()
        with self.assertRaises(ValueError):
            self.publish(attempt)
        self.assertEqual(self.snapshot(), before)

    def test_session_lock_survives_commit_and_rollback_and_releases_after_error(self):
        with psycopg.connect(self.database_url) as other:
            with self.assertRaisesRegex(RuntimeError, "fixture"):
                with product_publication_lock(self.connection):
                    self.connection.commit()
                    self.connection.rollback()
                    with self.assertRaises(RuntimeError):
                        with product_publication_lock(other):
                            self.fail("El bloqueo ya estaba ocupado.")
                    raise RuntimeError("fixture")
            with product_publication_lock(other):
                pass

    def test_pending_transactions_and_autocommit_are_rejected_without_confirming_work(self):
        run_id = begin_run(self.connection, "historical", MONTH, MONTH)
        with self.assertRaises(ValueError):
            publish_registered_captures(self.connection, run_id, [], self.root, as_of=AS_OF)
        with psycopg.connect(self.database_url, autocommit=True) as observer:
            self.assertEqual(observer.execute("SELECT count(*) FROM ops.runs").fetchone()[0], 0)
            with self.assertRaises(ValueError):
                with product_publication_lock(observer):
                    pass
        self.connection.rollback()

    def test_gold_helper_does_not_commit_and_caller_can_rollback_it(self):
        attempt = self.attempt()
        set_run_stage(self.connection, attempt[0], "silver")
        for capture_id, path in zip(attempt[1], attempt[2]):
            if path.name.endswith("_observations.json"):
                save_capture_observations(self.connection, attempt[0], capture_id, self.root)
        set_run_stage(self.connection, attempt[0], "gold")
        save_monthly_gold(self.connection, attempt[0], MONTH, MONTH, self.root, as_of=AS_OF)
        with psycopg.connect(self.database_url, autocommit=True) as observer:
            self.assertEqual(observer.execute("SELECT count(*) FROM mart.fx_monthly").fetchone()[0], 0)
        self.connection.rollback()
        self.assertEqual(self.connection.execute("SELECT count(*) FROM mart.grain_reference_monthly").fetchone()[0], 0)

    def test_unknown_calendar_year_is_logged_pending_and_blocks_publication(self):
        month = date(2027, 1, 1)
        attempt = self.attempt(start=month, end=month)
        with self.assertRaises(ValueError):
            self.publish(attempt, as_of=date(2027, 2, 1))
        self.assert_failed_without_facts(attempt[0], "quality")
        self.assertEqual(self.connection.execute("SELECT status FROM ops.dq_results WHERE rule_code = 'DQ-09'").fetchone()[0], "pending")
