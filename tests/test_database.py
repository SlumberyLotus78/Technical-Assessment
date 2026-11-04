"""Configuración y errores PostgreSQL sin consultar una base ni leer .env real."""

from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import psycopg

from grain_pipeline.common.config import load_database_url
from grain_pipeline.persistence.database import open_connection
from grain_pipeline.persistence.initialize import main


PRIVATE_VALUE = "fixture-do-not-print"
DATABASE_URL = f"postgresql://fixture:{PRIVATE_VALUE}@localhost:5432/fixture_database"


class DatabaseConfigurationTests(unittest.TestCase):
    """La conexión se lee de forma independiente de las credenciales API."""

    def test_database_configuration_works_without_api_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(f"DATABASE_URL={DATABASE_URL}\n", encoding="utf-8-sig")
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(load_database_url(path), DATABASE_URL)

    def test_environment_overrides_file_and_empty_values_require_correction(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(f"DATABASE_URL={DATABASE_URL}\n", encoding="utf-8")
            with patch.dict(os.environ, {"DATABASE_URL": "fixture-environment"}, clear=True):
                self.assertEqual(load_database_url(path), "fixture-environment")
            with patch.dict(os.environ, {"DATABASE_URL": ""}, clear=True):
                with self.assertRaises(ValueError) as error:
                    load_database_url(path)
            self.assertNotIn(PRIVATE_VALUE, str(error.exception))

    def test_database_configuration_preserves_literal_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("DATABASE_URL=postgresql://user:${PASSWORD}@localhost/db\n", encoding="utf-8")
            with patch.dict(os.environ, {"PASSWORD": "expanded"}, clear=True):
                self.assertIn("${PASSWORD}", load_database_url(path))


class DatabaseConnectionTests(unittest.TestCase):
    """Comprueba decisiones de conexión usando la API del driver simulada."""

    def test_missing_database_name_prevents_connection(self):
        with patch("grain_pipeline.persistence.database.psycopg.connect") as connect:
            with self.assertRaises(ValueError):
                open_connection("postgresql://user:fixture@localhost")
            connect.assert_not_called()

    def test_invalid_connection_string_excludes_its_original_value(self):
        with self.assertRaises(ValueError) as error:
            open_connection("unrecognized=" + PRIVATE_VALUE)
        self.assertNotIn(PRIVATE_VALUE, str(error.exception))

    def test_connection_has_bounded_wait_and_utc_session(self):
        connection = Mock()
        with patch("grain_pipeline.persistence.database.psycopg.connect", return_value=connection) as connect:
            self.assertIs(open_connection(DATABASE_URL), connection)
        connect.assert_called_once_with(DATABASE_URL, connect_timeout=10,
                                        application_name="grain_pipeline", options="-c timezone=UTC")

    def test_connection_error_excludes_private_driver_details(self):
        with patch("grain_pipeline.persistence.database.psycopg.connect",
                   side_effect=psycopg.OperationalError(DATABASE_URL)):
            with self.assertRaises(RuntimeError) as error:
                open_connection(DATABASE_URL)
        self.assertNotIn(PRIVATE_VALUE, str(error.exception))
        self.assertTrue(error.exception.__suppress_context__)


class DatabaseCommandTests(unittest.TestCase):
    """El comando informa errores controlados con código de salida uno."""

    def test_missing_configuration_does_not_open_a_connection(self):
        with patch("grain_pipeline.persistence.initialize.load_database_url",
                   side_effect=ValueError("Falta DATABASE_URL")):
            with patch("grain_pipeline.persistence.initialize.open_connection") as connect:
                with redirect_stderr(io.StringIO()):
                    self.assertEqual(main([]), 1)
                connect.assert_not_called()

    def test_sql_error_does_not_print_connection_or_original_message(self):
        output = io.StringIO()
        with patch("grain_pipeline.persistence.initialize.load_database_url", return_value=DATABASE_URL):
            with patch("grain_pipeline.persistence.initialize.open_connection",
                       side_effect=psycopg.OperationalError(DATABASE_URL)):
                with redirect_stderr(output):
                    self.assertEqual(main([]), 1)
        self.assertNotIn(PRIVATE_VALUE, output.getvalue())
