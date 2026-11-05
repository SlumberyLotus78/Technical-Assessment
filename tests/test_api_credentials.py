"""Encryption and local configuration checks using fictitious secrets."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dotenv import dotenv_values

from scripts.api_credentials import decrypt, encrypt, write_env


class ApiCredentialsTests(unittest.TestCase):
    def setUp(self):
        self.values = {"FRED_API_KEY": "fake-${LITERAL}", "BANXICO_TOKEN": "fake-'quoted\\token"}
        self.password = "a long fictitious password for tests"

    def test_round_trip_and_random_salt(self):
        first = encrypt(self.values, self.password)
        second = encrypt(self.values, self.password)
        self.assertNotEqual(first, second)
        self.assertEqual(decrypt(first, self.password), self.values)

    def test_wrong_password_and_tampering_are_rejected(self):
        document = encrypt(self.values, self.password)
        with self.assertRaises(ValueError):
            decrypt(document, "wrong password")
        document["token"] = "altered"
        with self.assertRaises(ValueError):
            decrypt(document, self.password)

    def test_update_preserves_database_and_literal_credentials(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("# keep comment\nDATABASE_URL=fixture-db\nFRED_API_KEY=old\nexport BANXICO_TOKEN=old\n", encoding="utf-8")
            write_env(path, self.values, Path("unused-template"))
            parsed = dotenv_values(path, interpolate=False)
            self.assertEqual(parsed["DATABASE_URL"], "fixture-db")
            for name, value in self.values.items():
                self.assertEqual(parsed[name], value)
            self.assertIn("# keep comment", path.read_text(encoding="utf-8"))

    def test_create_from_template(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            template = Path(directory) / "template"
            template.write_text("DATABASE_URL=\nFRED_API_KEY=\nBANXICO_TOKEN=\n", encoding="utf-8")
            write_env(path, self.values, template)
            self.assertEqual(dotenv_values(path, interpolate=False)["FRED_API_KEY"], self.values["FRED_API_KEY"])

    def test_short_password_rejected(self):
        with self.assertRaises(ValueError):
            encrypt(self.values, "short")
