"""Persistencia real sobre archivos ficticios y bases PostgreSQL desechables."""

from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from uuid import uuid4

import psycopg

from grain_pipeline.extraction.raw import save_capture
from grain_pipeline.persistence.captures import get_capture_record, register_capture
from grain_pipeline.persistence.catalog import prepare_catalog
from grain_pipeline.persistence.observations import save_capture_observations
from grain_pipeline.persistence.quality import record_capture_profile, record_quality_result
from grain_pipeline.persistence.runs import begin_run, fail_run, set_run_stage
from grain_pipeline.persistence.schema import apply_schema
from grain_pipeline.sources.catalog import SERIES
from tests.fixtures import metadata_record, observations_payload
from tests.postgres_support import PostgresTestCase


START, END = date(2026, 7, 1), date(2026, 9, 1)


def capture_file(root: Path, series=None, payload=None, kind="observations") -> Path:
    """Cada captura ficticia tiene carpeta propia, igual que un intento real."""
    series = SERIES[0] if series is None else series
    directory = root / uuid4().hex
    directory.mkdir()
    if kind == "metadata":
        return save_capture(directory, series, kind, metadata_record(series))
    payload = observations_payload(series) if payload is None else payload
    start = START if series["provider"] == "FRED" else END
    return save_capture(directory, series, kind, payload, start, date(2026, 9, 30))


class PostgresPersistenceTests(PostgresTestCase):
    """Las funciones reciben la conexión; cada caso verifica el resultado SQL."""

    def setUp(self):
        super().setUp()
        apply_schema(self.connection)
        prepare_catalog(self.connection)
        self.connection.commit()

    def test_run_stages_failure_and_private_error_details(self):
        run_id = begin_run(self.connection, "historical", START, END)
        set_run_stage(self.connection, run_id, "extraction")
        set_run_stage(self.connection, run_id, "quality")
        with self.assertRaises(ValueError):
            set_run_stage(self.connection, run_id, "planning")
        fail_run(self.connection, run_id, "quality", psycopg.OperationalError("fixture-private-password"))
        row = self.connection.execute(
            "SELECT status, stage, finished_at, error_summary FROM ops.runs WHERE run_id = %s", (run_id,)).fetchone()
        self.assertEqual(row[:2], ("failed", "quality"))
        self.assertIsNotNone(row[2])
        self.assertNotIn("fixture-private-password", row[3])
        with self.assertRaises(ValueError):
            set_run_stage(self.connection, run_id, "silver")

    def test_invalid_plans_and_autocommit_are_rejected(self):
        cases = (("other", START, END), ("historical", START, None),
                 ("historical", END, START), ("historical", date(2026, 7, 2), END))
        for mode, start, end in cases:
            with self.subTest(mode=mode, start=start, end=end):
                with self.assertRaises(ValueError):
                    begin_run(self.connection, mode, start, end)
        with psycopg.connect(self.database_url, autocommit=True) as connection:
            with self.assertRaises(ValueError):
                begin_run(connection, "historical", START, END)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM ops.runs").fetchone()[0], 0)

    def test_capture_registration_is_repeatable_without_reassigning_original_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_run = begin_run(self.connection, "historical", START, END)
            path = capture_file(root)
            first_id = register_capture(self.connection, first_run, path, root)
            self.assertEqual(register_capture(self.connection, first_run, path, root), first_id)
            second_run = begin_run(self.connection, "historical", START, END)
            self.assertEqual(register_capture(self.connection, second_run, path, root), first_id)
            row = self.connection.execute("SELECT run_id, content_sha256 FROM ops.raw_captures").fetchall()
            self.assertEqual(row, [(first_run, sha256(path.read_bytes()).hexdigest())])

    def test_modified_capture_is_detected_before_any_observation_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = begin_run(self.connection, "historical", START, END)
            path = capture_file(root)
            capture_id = register_capture(self.connection, run_id, path, root)
            original_hash = get_capture_record(self.connection, capture_id)["content_sha256"]
            body = json.loads(path.read_text(encoding="utf-8"))
            body["payload"]["observations"][0]["value"] = "999"
            path.write_text(json.dumps(body), encoding="utf-8")
            with self.assertRaises(ValueError):
                register_capture(self.connection, run_id, path, root)
            with self.assertRaises(ValueError):
                save_capture_observations(self.connection, run_id, capture_id, root)
            self.assertEqual(get_capture_record(self.connection, capture_id)["content_sha256"], original_hash)
            self.assertEqual(self.connection.execute("SELECT count(*) FROM core.observations").fetchone()[0], 0)

    def test_initial_insert_and_unchanged_repeat_preserve_precision_and_audit_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = begin_run(self.connection, "historical", START, END)
            capture_id = register_capture(self.connection, run_id, capture_file(root), root)
            self.assertEqual(save_capture_observations(self.connection, run_id, capture_id, root),
                             {"received": 3, "written": 3, "unchanged": 0})
            query = """SELECT observation_date, value, source_capture_id, created_run_id, updated_run_id,
                       created_at, updated_at FROM core.observations ORDER BY observation_date"""
            before = self.connection.execute(query).fetchall()
            self.assertEqual(before[0][1], Decimal("100.1234567890123456789"))
            self.assertEqual(save_capture_observations(self.connection, run_id, capture_id, root),
                             {"received": 3, "written": 0, "unchanged": 3})
            self.assertEqual(self.connection.execute(query).fetchall(), before)
            # Una captura nueva con los mismos valores tampoco modifica la fila vigente.
            second_run = begin_run(self.connection, "historical", START, END)
            second_capture = register_capture(self.connection, second_run, capture_file(root), root)
            self.assertEqual(save_capture_observations(self.connection, second_run, second_capture, root)["written"], 0)
            self.assertEqual(self.connection.execute(query).fetchall(), before)

    def test_source_revision_updates_only_the_changed_row_and_preserves_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_run = begin_run(self.connection, "historical", START, END)
            first_path = capture_file(root)
            first_bytes = first_path.read_bytes()
            first_capture = register_capture(self.connection, first_run, first_path, root)
            save_capture_observations(self.connection, first_run, first_capture, root)
            revised = observations_payload(SERIES[0])
            revised["observations"][1]["value"] = "103.1250000000000000001"
            second_run = begin_run(self.connection, "historical", START, END)
            second_capture = register_capture(self.connection, second_run, capture_file(root, payload=revised), root)
            self.assertEqual(save_capture_observations(self.connection, second_run, second_capture, root),
                             {"received": 3, "written": 1, "unchanged": 2})
            row = self.connection.execute(
                """SELECT value, created_run_id, updated_run_id, source_capture_id FROM core.observations
                   WHERE observation_date = '2026-08-01'""").fetchone()
            self.assertEqual(row, (Decimal("103.1250000000000000001"), first_run, second_run, second_capture))
            self.assertEqual(first_path.read_bytes(), first_bytes)
            self.assertEqual(self.connection.execute("SELECT count(*) FROM ops.raw_captures").fetchone()[0], 2)

    def test_failed_data_preserves_committed_dq_without_publishing_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = observations_payload(SERIES[0])
            payload["observations"][1]["value"] = "."
            run_id = begin_run(self.connection, "historical", START, END)
            capture_id = register_capture(self.connection, run_id, capture_file(root, payload=payload), root)
            set_run_stage(self.connection, run_id, "quality")
            profile = record_capture_profile(self.connection, run_id, capture_id, root)
            self.assertTrue(profile["has_issues"])
            self.connection.commit()  # Diagnóstico durable antes de una publicación.
            with self.assertRaises(ValueError):
                with psycopg.connect(self.database_url) as publishing:
                    save_capture_observations(publishing, run_id, capture_id, root)
            fail_run(self.connection, run_id, "silver", ValueError("fixture-private-detail"))
            self.connection.commit()
            failed = self.connection.execute(
                "SELECT rule_code FROM ops.dq_results WHERE status = 'failed' ORDER BY rule_code").fetchall()
            self.assertEqual(failed, [("DQ-04",), ("DQ-08",)])
            self.assertEqual(self.connection.execute("SELECT count(*) FROM core.observations").fetchone()[0], 0)
            self.assertEqual(self.connection.execute("SELECT count(*) FROM ops.watermarks").fetchone()[0], 0)

    def test_helpers_leave_commit_and_rollback_to_the_coordinator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = begin_run(self.connection, "historical", START, END)
            capture_id = register_capture(self.connection, run_id, capture_file(root), root)
            save_capture_observations(self.connection, run_id, capture_id, root)
            with psycopg.connect(self.database_url) as observer:
                self.assertEqual(observer.execute("SELECT count(*) FROM ops.runs").fetchone()[0], 0)
                self.assertEqual(observer.execute("SELECT count(*) FROM core.observations").fetchone()[0], 0)
            self.connection.rollback()
            self.assertEqual(self.connection.execute("SELECT count(*) FROM ops.raw_captures").fetchone()[0], 0)

    def test_wrong_capture_type_plan_interval_and_closed_run_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            short_run = begin_run(self.connection, "historical", END, END)
            capture_id = register_capture(self.connection, short_run, capture_file(root), root)
            with self.assertRaises(ValueError):
                save_capture_observations(self.connection, short_run, capture_id, root)
            run_id = begin_run(self.connection, "historical", START, END)
            metadata = register_capture(self.connection, run_id, capture_file(root, kind="metadata"), root)
            with self.assertRaises(ValueError):
                save_capture_observations(self.connection, run_id, metadata, root)
            fail_run(self.connection, run_id, "quality", ValueError("fixture failure"))
            with self.assertRaises(ValueError):
                register_capture(self.connection, run_id, capture_file(root), root)
            with self.assertRaises(ValueError):
                record_capture_profile(self.connection, run_id, capture_id, root)

    def test_profile_rules_are_saved_with_provenance_and_daily_calendar_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = begin_run(self.connection, "historical", START, END)
            for series in (SERIES[0], SERIES[3]):
                capture_id = register_capture(self.connection, run_id, capture_file(root, series=series), root)
                record_capture_profile(self.connection, run_id, capture_id, root)
            checks = self.connection.execute("SELECT rule_code, status, series_code, details FROM ops.dq_results").fetchall()
            self.assertEqual(len(checks), 17)
            pending = [(code, status, series) for code, status, series, _ in checks if status == "pending"]
            self.assertEqual(pending, [("DQ-09", "pending", "SF43718")])
            self.assertTrue(all("capture_id" in details for _, _, _, details in checks))
            record_quality_result(self.connection, run_id, rule_code="PUB-01", status="pending",
                                  details={"reason": "Gold dependencies required"}, period_start=START, period_end=END)
            self.assertEqual(self.connection.execute(
                "SELECT provider, series_code FROM ops.dq_results WHERE rule_code = 'PUB-01'").fetchone(), (None, None))

    def test_catalog_or_registered_source_context_changes_block_silver(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = begin_run(self.connection, "historical", START, END)
            capture_id = register_capture(self.connection, run_id, capture_file(root), root)
            self.connection.commit()
            self.connection.execute("UPDATE core.series SET unit = 'fixture-other' WHERE series_code = 'PMAIZMTUSDM'")
            with self.assertRaises(RuntimeError):
                save_capture_observations(self.connection, run_id, capture_id, root)
            self.connection.rollback()
            self.connection.execute("UPDATE ops.raw_captures SET series_code = 'PWHEAMTUSDM' WHERE capture_id = %s", (capture_id,))
            with self.assertRaises(ValueError):
                save_capture_observations(self.connection, run_id, capture_id, root)
            self.assertEqual(self.connection.execute("SELECT count(*) FROM core.observations").fetchone()[0], 0)
