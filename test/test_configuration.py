"""Comprobaciones de configuración con archivos y claves ficticias."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from grain_pipeline.common.config import load_credentials


class CredentialConfigurationTests(unittest.TestCase):
    def test_file_values_remain_literal_and_accept_utf8_bom(self):
        with TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "FRED_API_KEY=fixture-${SUFFIX}\nBANXICO_TOKEN=fixture-banxico\n",
                encoding="utf-8-sig",
            )
            with patch.dict(os.environ, {"SUFFIX": "expanded"}, clear=True):
                credentials = load_credentials(env_file)

        self.assertEqual(credentials["FRED_API_KEY"], "fixture-${SUFFIX}")
        self.assertEqual(credentials["BANXICO_TOKEN"], "fixture-banxico")

    def test_environment_value_overrides_file_value(self):
        with TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "FRED_API_KEY=fixture-file\nBANXICO_TOKEN=fixture-banxico\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"FRED_API_KEY": "fixture-environment"}, clear=True):
                credentials = load_credentials(env_file)

        self.assertEqual(credentials["FRED_API_KEY"], "fixture-environment")
        self.assertEqual(credentials["BANXICO_TOKEN"], "fixture-banxico")

    def test_empty_environment_value_requires_correction(self):
        with TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "FRED_API_KEY=fixture-file\nBANXICO_TOKEN=fixture-banxico\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"FRED_API_KEY": ""}, clear=True):
                with self.assertRaises(ValueError) as error:
                    load_credentials(env_file)

        self.assertIn("FRED_API_KEY", str(error.exception))

    def test_missing_credential_message_excludes_available_value(self):
        available_value = "fixture-do-not-print-this-value"
        with TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(f"FRED_API_KEY={available_value}\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ValueError) as error:
                    load_credentials(env_file)

        message = str(error.exception)
        self.assertIn("BANXICO_TOKEN", message)
        self.assertNotIn(available_value, message)
