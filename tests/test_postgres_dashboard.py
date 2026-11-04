"""Lectura del dashboard sobre PostgreSQL real aislado, con permisos e instantáneas."""

from datetime import date
from decimal import Decimal
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from streamlit.testing.v1 import AppTest

from app.analytics import build_analysis
from app.queries import open_dashboard_connection, read_dashboard_snapshot
from grain_pipeline.orchestration.historical import run_historical
from grain_pipeline.orchestration.incremental import run_incremental
from grain_pipeline.persistence.catalog import prepare_catalog
from grain_pipeline.persistence.schema import apply_schema
from tests.historical_fixtures import CREDENTIALS, historical_session
from tests.postgres_support import PostgresTestCase


JULY, SEPTEMBER, TODAY = date(2026, 7, 1), date(2026, 9, 1), date(2026, 11, 3)


class PostgresDashboardTests(PostgresTestCase):
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

    def test_uninitialized_product_returns_a_controlled_empty_snapshot(self):
        self.assertEqual(read_dashboard_snapshot(self.database_url), {"publication": None, "rows": []})

    def test_published_snapshot_has_decimal_values_and_does_not_change_control(self):
        initial = self.seed()
        before = self.connection.execute("SELECT * FROM ops.watermarks").fetchall()
        self.connection.commit()
        snapshot = read_dashboard_snapshot(self.database_url)
        self.assertEqual(str(snapshot["publication"]["last_run_id"]), initial["run_id"])
        self.assertEqual(len(snapshot["rows"]), 9)
        self.assertIsInstance(snapshot["rows"][0]["reference_mxn_t"], Decimal)
        self.assertEqual(len(build_analysis(snapshot["rows"], JULY, SEPTEMBER)["summary"]), 3)
        self.assertEqual(self.connection.execute("SELECT * FROM ops.watermarks").fetchall(), before)

    def test_readonly_connection_rejects_writes_even_with_an_admin_account(self):
        with open_dashboard_connection(self.database_url) as reader:
            self.assertEqual(reader.execute("SHOW transaction_read_only").fetchone()[0], "on")
            with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
                reader.execute("DELETE FROM ops.watermarks")
            reader.rollback()

    def test_a_select_only_login_can_read_the_dashboard(self):
        self.seed()
        role = "grain_reader_" + uuid4().hex
        password = uuid4().hex
        self.admin.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
            sql.Identifier(role), sql.Literal(password)))
        def remove_role():
            self.connection.rollback()
            self.connection.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            self.connection.commit()
            self.admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
        self.addCleanup(remove_role)
        self.admin.execute(sql.SQL("GRANT {} TO {} WITH INHERIT TRUE").format(
            sql.Identifier(role), sql.Identifier(self.admin.info.user)))
        self.connection.execute(sql.SQL("GRANT USAGE ON SCHEMA core, mart, ops TO {}").format(sql.Identifier(role)))
        self.connection.execute(sql.SQL("GRANT SELECT ON core.series, mart.fx_monthly, mart.grain_reference_monthly, ops.watermarks, ops.runs, ops.schema_migrations TO {}").format(sql.Identifier(role)))
        self.connection.commit()
        snapshot = read_dashboard_snapshot(make_conninfo(self.database_url, user=role, password=password))
        self.assertEqual(len(snapshot["rows"]), 9)

    def test_corrupt_gold_is_reported_instead_of_plotting_partial_or_wrong_values(self):
        self.seed()
        self.connection.execute("UPDATE mart.grain_reference_monthly SET reference_mxn_t = reference_mxn_t + 1 WHERE month = %s", (SEPTEMBER,))
        self.connection.commit()
        with self.assertRaises(ValueError):
            read_dashboard_snapshot(self.database_url)

    def test_repeatable_read_does_not_mix_two_publications(self):
        initial = self.seed()
        with open_dashboard_connection(self.database_url) as reader:
            reader.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            before = reader.execute("SELECT last_run_id FROM ops.watermarks").fetchone()[0]
            run_incremental(self.connection, historical_session(latest_month=date(2026, 10, 1)), CREDENTIALS,
                            self.root, as_of=TODAY)
            self.assertEqual(reader.execute("SELECT count(*) FROM mart.grain_reference_monthly").fetchone()[0], 9)
            self.assertEqual(reader.execute("SELECT last_run_id FROM ops.watermarks").fetchone()[0], before)
            self.assertEqual(str(before), initial["run_id"])
        self.assertEqual(len(read_dashboard_snapshot(self.database_url)["rows"]), 12)

    def test_interface_runs_against_the_real_readonly_query_and_reacts_to_filters(self):
        self.seed()
        app_file = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
        with patch.dict(os.environ, {"READONLY_DATABASE_URL": self.database_url, "GRAIN_ENV_FILE": "missing-fixture.env"}):
            app = AppTest.from_file(str(app_file), default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertEqual(len(app.get("plotly_chart")), 3)
            app.selectbox(key="grain").select("PSOYBUSDM").run()
            app.selectbox(key="start_month").select(SEPTEMBER).run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertEqual(app.metric[0].value, "$2,000.00")
