"""Integración PostgreSQL optativa en bases desechables, nunca desde .env.

TEST_DATABASE_URL debe señalar una base de prueba cuyo nombre empiece por
grain_test_. Su usuario necesita CREATEDB. Cada caso crea y elimina una base
propia grain_test_<uuid>; sin esa variable, unittest omite estos casos.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from datetime import date
from decimal import Decimal
import io
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from grain_pipeline.persistence.catalog import prepare_catalog
from grain_pipeline.persistence.initialize import main
from grain_pipeline.persistence.schema import apply_schema, verify_schema


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(TEST_DATABASE_URL, "Requiere TEST_DATABASE_URL y una base de prueba dedicada.")
class PostgresSchemaTests(unittest.TestCase):
    """Comprueba SQL real, transacciones, repetición y restricciones de datos."""

    def setUp(self):
        # Validamos el destino antes de crear nada.
        params = conninfo_to_dict(TEST_DATABASE_URL)
        if not params.get("dbname", "").startswith("grain_test_"):
            raise ValueError("La base de TEST_DATABASE_URL debe comenzar por grain_test_.")
        self.admin = psycopg.connect(TEST_DATABASE_URL, autocommit=True)
        self.addCleanup(self.admin.close)
        self.database_name = "grain_test_" + uuid4().hex
        # Identifier compone un nombre SQL, los valores de filas usarán %s.
        self.admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
            sql.Identifier(self.database_name)))
        self.addCleanup(self.drop_test_database)
        self.database_url = make_conninfo(TEST_DATABASE_URL, dbname=self.database_name)
        self.connection = psycopg.connect(self.database_url)
        self.addCleanup(self.connection.close)

    def drop_test_database(self):
        """Elimina exclusivamente la base UUID creada por este caso."""
        if re.fullmatch(r"grain_test_[0-9a-f]{32}", self.database_name) is None:
            raise ValueError("Nombre de limpieza de prueba incompatible.")
        self.admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
            sql.Identifier(self.database_name)))

    def install(self):
        apply_schema(self.connection)
        prepare_catalog(self.connection)
        self.connection.commit()

    def seed_lineage(self):
        """Prepara referencias ficticias para probar las restricciones de filas."""
        run_id, capture_id = uuid4(), uuid4()
        self.connection.execute(
            """INSERT INTO ops.runs (run_id, load_type, status, stage, start_month, end_month)
               VALUES (%s, 'historical', 'running', 'extraction', '2026-09-01', '2026-09-01')""", (run_id,))
        self.connection.execute(
            """INSERT INTO ops.raw_captures
               (capture_id, run_id, provider, series_code, kind, storage_path, content_sha256,
                captured_at, window_start, window_end)
               VALUES (%s, %s, 'FRED', 'PMAIZMTUSDM', 'observations', %s, %s,
                       CURRENT_TIMESTAMP, '2026-09-01', '2026-09-30')""",
            (capture_id, run_id, f"fixture/{capture_id}.json", "a" * 64))
        return run_id, capture_id

    def insert_observation(self, run_id, capture_id, value, day=date(2026, 9, 1)):
        self.connection.execute(
            """INSERT INTO core.observations
               (provider, series_code, observation_date, value, source_capture_id, created_run_id, updated_run_id)
               VALUES ('FRED', 'PMAIZMTUSDM', %s, %s, %s, %s, %s)""",
            (day, value, capture_id, run_id, run_id))

    def test_initialize_twice_and_check_only_preserve_catalog_and_empty_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(f"DATABASE_URL={self.database_url}\n", encoding="utf-8")
            # El archivo contiene únicamente la conexión desechable del caso.
            with patch.dict(os.environ, {}, clear=True):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["--env-file", str(path)]), 0)
                    self.assertEqual(main(["--env-file", str(path)]), 0)
                    self.assertEqual(main(["--env-file", str(path), "--check-only"]), 0)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM core.series").fetchone()[0], 4)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM ops.schema_migrations").fetchone()[0], 1)
        for table in ("core.observations", "ops.runs", "ops.watermarks", "mart.fx_monthly",
                      "mart.grain_reference_monthly"):
            query = sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(*table.split(".")))
            self.assertEqual(self.connection.execute(query).fetchone()[0], 0)

    def test_failure_rolls_back_schema_catalog_and_version_together(self):
        with self.assertRaises(RuntimeError):
            with psycopg.connect(self.database_url) as connection:
                apply_schema(connection)
                prepare_catalog(connection)
                raise RuntimeError("fixture failure before commit")
        for name in ("core.series", "ops.schema_migrations", "mart.fx_monthly"):
            self.assertIsNone(self.connection.execute("SELECT to_regclass(%s)", (name,)).fetchone()[0])

    def test_occupied_unversioned_schema_is_preserved(self):
        self.connection.execute("CREATE SCHEMA core; CREATE TABLE core.legacy (value INTEGER)")
        self.connection.execute("INSERT INTO core.legacy VALUES (7)")
        self.connection.commit()
        with self.assertRaises(RuntimeError):
            with psycopg.connect(self.database_url) as connection:
                apply_schema(connection)
        self.assertEqual(self.connection.execute("SELECT value FROM core.legacy").fetchone()[0], 7)
        self.assertIsNone(self.connection.execute("SELECT to_regclass('ops.schema_migrations')").fetchone()[0])

    def test_catalog_mismatch_is_detected_without_overwriting_existing_unit(self):
        self.install()
        self.connection.execute("UPDATE core.series SET unit = 'fixture-other' WHERE series_code = 'PMAIZMTUSDM'")
        self.connection.commit()
        with self.assertRaises(RuntimeError):
            with psycopg.connect(self.database_url) as connection:
                apply_schema(connection)
                prepare_catalog(connection)
        row = self.connection.execute("SELECT unit FROM core.series WHERE series_code = 'PMAIZMTUSDM'").fetchone()
        self.assertEqual(row[0], "fixture-other")

    def test_modified_migration_checksum_or_missing_table_are_detected(self):
        self.install()
        self.connection.execute("UPDATE ops.schema_migrations SET checksum = %s", ("0" * 64,))
        with self.assertRaises(RuntimeError):
            verify_schema(self.connection)
        # Revertimos la alteración ficticia antes de comprobar una tabla ausente.
        self.connection.rollback()
        self.connection.execute("DROP TABLE mart.grain_reference_monthly")
        with self.assertRaises(RuntimeError):
            verify_schema(self.connection)

    def test_numeric_precision_duplicate_keys_and_foreign_keys(self):
        self.install()
        run_id, capture_id = self.seed_lineage()
        value = Decimal("236.9161241071429123456789")
        self.insert_observation(run_id, capture_id, value)
        actual = self.connection.execute("SELECT value FROM core.observations").fetchone()[0]
        self.assertEqual(actual, value)
        with self.assertRaises(psycopg.errors.UniqueViolation):
            with self.connection.transaction():
                self.insert_observation(run_id, capture_id, value)
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            with self.connection.transaction():
                self.insert_observation(run_id, uuid4(), value, date(2026, 9, 2))

    def test_missing_non_positive_and_non_finite_values_are_rejected(self):
        self.install()
        run_id, capture_id = self.seed_lineage()
        for value in (None, Decimal("0"), Decimal("-1"), Decimal("NaN"),
                      Decimal("Infinity"), Decimal("-Infinity")):
            with self.subTest(value=str(value)):
                with self.assertRaises(psycopg.IntegrityError):
                    with self.connection.transaction():
                        self.insert_observation(run_id, capture_id, value)

    def test_run_status_and_paired_month_constraints(self):
        self.install()
        cases = (("running", "planning", "2026-09-01", None, None),
                 ("running", "planning", "2026-09-02", "2026-09-02", None),
                 ("succeeded", "publication", None, None, "2026-11-03T22:00:00Z"),
                 ("succeeded", "gold", "2026-09-01", "2026-09-01", "2026-11-03T22:00:00Z"),
                 ("failed", "quality", "2026-09-01", "2026-09-01", "2026-11-03T22:00:00Z"))
        for status, stage, start, end, finished in cases:
            with self.subTest(status=status, stage=stage, start=start, end=end):
                with self.assertRaises(psycopg.IntegrityError):
                    with self.connection.transaction():
                        self.connection.execute(
                            """INSERT INTO ops.runs
                               (run_id, load_type, status, stage, start_month, end_month, started_at, finished_at)
                               VALUES (%s, 'historical', %s, %s, %s, %s, '2026-11-03T21:00:00Z', %s)""",
                            (uuid4(), status, stage, start, end, finished))

    def test_gold_accepts_negative_variation_but_rejects_non_finite_values_and_bad_counts(self):
        self.install()
        run_id, capture_id = self.seed_lineage()
        self.insert_observation(run_id, capture_id, Decimal("100"))
        with self.assertRaises(psycopg.errors.CheckViolation):
            with self.connection.transaction():
                self.connection.execute(
                    """INSERT INTO mart.fx_monthly VALUES
                       ('Banxico', 'SF43718', '2026-09-01', 18, 20, 21, 'fixture-calendar', %s, CURRENT_TIMESTAMP)""",
                    (run_id,))
        self.connection.execute(
            """INSERT INTO mart.fx_monthly VALUES
               ('Banxico', 'SF43718', '2026-09-01', 18, 21, 21, 'fixture-calendar', %s, CURRENT_TIMESTAMP)""", (run_id,))
        self.connection.execute(
            """INSERT INTO mart.grain_reference_monthly VALUES
               ('FRED', 'PMAIZMTUSDM', '2026-09-01', 'Banxico', 'SF43718',
                100, 18, 1800, -2.5, NULL, %s, CURRENT_TIMESTAMP)""", (run_id,))
        for value in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
            with self.subTest(value=str(value)):
                with self.assertRaises(psycopg.errors.CheckViolation):
                    with self.connection.transaction():
                        self.connection.execute("UPDATE mart.grain_reference_monthly SET mom_change_pct = %s", (value,))
        row = self.connection.execute("SELECT mom_change_pct, yoy_change_pct FROM mart.grain_reference_monthly").fetchone()
        self.assertEqual(row, (Decimal("-2.5"), None))

    def test_dq_scope_and_watermark_interval_constraints(self):
        self.install()
        run_id, _ = self.seed_lineage()
        with self.assertRaises(psycopg.errors.CheckViolation):
            with self.connection.transaction():
                self.connection.execute(
                    """INSERT INTO ops.dq_results VALUES
                       (%s, %s, 'DQ-01', 'FRED', NULL, '2026-09-01', '2026-09-30',
                        'passed', '{}'::jsonb, CURRENT_TIMESTAMP)""", (uuid4(), run_id))
        for start, end in (("2026-09-02", "2026-09-01"), ("2026-10-01", "2026-09-01")):
            with self.assertRaises(psycopg.errors.CheckViolation):
                with self.connection.transaction():
                    self.connection.execute(
                        "INSERT INTO ops.watermarks VALUES ('grain_reference_mxn', %s, %s, %s, %s, CURRENT_TIMESTAMP)",
                        (start, end, run_id, run_id))

    def test_concurrent_preparation_creates_one_version_and_one_catalog(self):
        def prepare():
            with psycopg.connect(self.database_url) as connection:
                created = apply_schema(connection)
                prepare_catalog(connection)
                return created
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: prepare(), range(2)))
        self.assertEqual(sorted(outcomes), [False, True])
        self.assertEqual(self.connection.execute("SELECT count(*) FROM core.series").fetchone()[0], 4)
