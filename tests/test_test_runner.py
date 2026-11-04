"""Configuración explícita de integración, sin leer el .env real ni conectar."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.run import read_test_database_url


class TestRunnerConfigurationTests(unittest.TestCase):
    """La variable de producción nunca habilita ni dirige las pruebas SQL."""

    def test_project_database_url_is_not_used_as_a_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("DATABASE_URL=postgresql://fixture@localhost/fred_banxico\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
                read_test_database_url(path)

    def test_test_connection_is_read_without_interpolation_and_environment_has_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            url = "postgresql://fixture:fixture-only@localhost/grain_test_fixture"
            path.write_text("TEST_DATABASE_URL=" + url + "\n", encoding="utf-8-sig")
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(read_test_database_url(path), url)
            other = "postgresql://fixture@localhost/grain_test_other"
            with patch.dict(os.environ, {"TEST_DATABASE_URL": other}, clear=True):
                self.assertEqual(read_test_database_url(path), other)

    def test_empty_invalid_and_non_test_database_connections_are_rejected_privately(self):
        values = ("", "unrecognized=fixture-private", "postgresql://fixture:fixture-private@localhost/fred_banxico")
        for value in values:
            with self.subTest(value=value), patch.dict(os.environ, {"TEST_DATABASE_URL": value}, clear=True):
                with self.assertRaises(ValueError) as caught:
                    read_test_database_url(Path("unused.env"))
                self.assertNotIn("fixture-private", str(caught.exception))
