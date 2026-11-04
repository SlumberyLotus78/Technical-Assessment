"""Preflight del scheduler en una base propia y transacciones de solo lectura."""

from contextlib import redirect_stdout
from datetime import date
import io
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

import psycopg

from grain_pipeline.orchestration.historical import run_historical
from grain_pipeline.orchestration.state import check_published_state, main
from grain_pipeline.persistence.catalog import prepare_catalog
from grain_pipeline.persistence.schema import apply_schema
from tests.historical_fixtures import CREDENTIALS, historical_session
from tests.postgres_support import PostgresTestCase


JULY, SEPTEMBER, TODAY = date(2026, 7, 1), date(2026, 9, 1), date(2026, 11, 3)


class PostgresStateTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        apply_schema(self.connection)
        prepare_catalog(self.connection)
        self.connection.commit()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "bronze"

    def seed(self):
        return run_historical(self.connection, historical_session(), CREDENTIALS, self.root, JULY, SEPTEMBER, as_of=TODAY)

    def read_only_check(self):
        with psycopg.connect(self.database_url) as reader:
            reader.read_only = True
            reader.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
            return check_published_state(reader, self.root, as_of=TODAY)

    def test_missing_historical_publication_is_not_ready_and_creates_no_run(self):
        with self.assertRaises(ValueError):
            self.read_only_check()
        self.assertEqual(self.connection.execute("SELECT count(*) FROM ops.runs").fetchone()[0], 0)

    def test_complete_product_is_checked_without_locks_or_writes(self):
        self.seed()
        before = self.connection.execute("SELECT * FROM ops.watermarks").fetchall()
        self.connection.commit()
        result = self.read_only_check()
        self.assertTrue(result["ready"])
        self.assertEqual((result["silver_rows"], result["fx_months"], result["grain_references"]), (74, 3, 9))
        self.assertEqual(self.connection.execute("SELECT * FROM ops.watermarks").fetchall(), before)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM ops.runs").fetchone()[0], 1)

    def test_modified_originals_or_gold_prevent_registration_readiness(self):
        self.seed()
        self.connection.execute("UPDATE mart.grain_reference_monthly SET reference_mxn_t = reference_mxn_t + 1 WHERE month = %s", (SEPTEMBER,))
        self.connection.commit()
        with self.assertRaises(ValueError):
            self.read_only_check()
        self.connection.execute("UPDATE mart.grain_reference_monthly SET reference_mxn_t = reference_mxn_t - 1 WHERE month = %s", (SEPTEMBER,))
        self.connection.commit()
        path = next((self.root / "historical").rglob("*SF43718_observations.json"), None)
        if path is None:
            path = next(path for path in (self.root / "historical").rglob("*.json") if '"kind": "observations"' in path.read_text(encoding="utf-8"))
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.read_only_check()

    def test_cli_works_without_api_keys_and_exports_only_public_state(self):
        self.seed()
        env_file, report = self.root.parent / "fixture.env", self.root.parent / "state.json"
        env_file.write_text("DATABASE_URL=" + self.database_url, encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--env-file", str(env_file), "--bronze-root", str(self.root), "--report", str(report)]), 0)
        result = json.loads(report.read_text(encoding="utf-8"))
        self.assertTrue(result["ready"])
        self.assertNotIn("database_url", result)
