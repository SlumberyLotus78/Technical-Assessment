"""Interacción y privacidad de la interfaz mediante Streamlit AppTest, sin servidor SQL."""

from datetime import datetime, timezone
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import psycopg
from streamlit.testing.v1 import AppTest

from tests.analytical_fixtures import analytical_rows


APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


class DashboardInteractionTests(unittest.TestCase):
    def test_filters_units_and_one_month_selection_keep_three_charts(self):
        rows = analytical_rows()
        publication = {"start_month": rows[0]["month"], "published_through_month": max(row["month"] for row in rows),
                       "updated_at": datetime(2026, 11, 3, tzinfo=timezone.utc)}
        with patch.dict(os.environ, {"DATABASE_URL": "fixture-only", "READONLY_DATABASE_URL": "fixture-only", "GRAIN_ENV_FILE": "missing-fixture.env"}), \
                patch("app.queries.read_dashboard_snapshot", return_value={"publication": publication, "rows": rows}):
            app = AppTest.from_file(str(APP), default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertEqual(len(app.get("plotly_chart")), 3)
            app.selectbox(key="grain").select("PWHEAMTUSDM").run()
            app.radio[0].set_value("MXN/t").run()
            app.selectbox(key="start_month").select(publication["published_through_month"]).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.get("plotly_chart")), 3)
            self.assertEqual(app.metric[2].value, "+0.00%")

    def test_missing_configuration_and_database_errors_are_controlled_and_private(self):
        with patch.dict(os.environ, {"DATABASE_URL": "", "READONLY_DATABASE_URL": "", "GRAIN_ENV_FILE": "missing-fixture.env"}):
            app = AppTest.from_file(str(APP), default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertIn("DATABASE_URL", app.error[0].value)
        with patch.dict(os.environ, {"DATABASE_URL": "fixture-only", "READONLY_DATABASE_URL": "fixture-only", "GRAIN_ENV_FILE": "missing-fixture.env"}), \
                patch("app.queries.read_dashboard_snapshot", side_effect=psycopg.OperationalError("private-password-and-dsn")):
            app = AppTest.from_file(str(APP), default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertNotIn("private-password", app.error[0].value)
