"""Muestra completa con APIs simuladas y capturas en carpetas temporales."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import date, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from grain_pipeline.extraction.raw import create_sample_directory, save_capture, write_json
from grain_pipeline.extraction.sample import collect_sample, main
from grain_pipeline.sources.catalog import SERIES
from tests.fixtures import metadata_payload, observations_payload


CREDENTIALS = {"FRED_API_KEY": "fixture-fred-key", "BANXICO_TOKEN": "fixture-banxico-token"}
TODAY = date(2026, 11, 3)


class SampleCollectionTests(unittest.TestCase):
    """Reutiliza el código real de contratos, selección, captura y perfil."""

    def collect(self, directory, payloads=None):
        """Sustituye solo las dos referencias al transporte HTTP de las fuentes."""
        if payloads is None:
            payloads = [observations_payload(series) for series in SERIES]
        with patch("grain_pipeline.sources.metadata.request_json",
                   side_effect=[metadata_payload(series) for series in SERIES]) as metadata_request:
            with patch("grain_pipeline.sources.observations.request_json", side_effect=payloads) as data_request:
                result = collect_sample(Mock(), CREDENTIALS, directory, TODAY)
        self.assertEqual(metadata_request.call_count, 4)
        self.assertEqual(data_request.call_count, 4)
        return result

    def test_full_sample_preserves_eight_captures_and_writes_a_serializable_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = create_sample_directory(Path(temporary))
            result = self.collect(directory)
            self.assertEqual(result["sample_month"], "2026-09")
            self.assertFalse(result["has_issues"])
            self.assertEqual([item["rows"] for item in result["profiles"]], [3, 3, 3, 2])
            self.assertEqual(len(list(directory.glob("*.json"))), 9)
            report_text = (directory / "profile.json").read_text(encoding="utf-8")
            self.assertEqual(json.loads(report_text), result)
            for series in SERIES:
                capture = directory / f"{series['provider'].lower()}_{series['code']}_observations.json"
                content = capture.read_text(encoding="utf-8")
                self.assertEqual(json.loads(content)["payload"], observations_payload(series))
                for private_value in CREDENTIALS.values():
                    self.assertNotIn(private_value, content)

    def test_value_issues_still_produce_a_profile_for_all_four_series(self):
        payloads = [observations_payload(series) for series in SERIES]
        payloads[0]["observations"][1]["value"] = "."
        with tempfile.TemporaryDirectory() as temporary:
            directory = create_sample_directory(Path(temporary))
            result = self.collect(directory, payloads)
            self.assertTrue(result["has_issues"])
            self.assertEqual(len(result["profiles"]), 4)
            self.assertEqual(result["profiles"][0]["missing_months"], ["2026-08-01"])
            capture = json.loads((directory / "fred_PMAIZMTUSDM_observations.json").read_text(encoding="utf-8"))
            self.assertEqual(capture["payload"]["observations"][1]["value"], ".")

    def test_contract_failure_keeps_the_incompatible_capture_without_a_completion_report(self):
        payloads = [observations_payload(series) for series in SERIES]
        payloads[3]["bmx"]["series"][0]["idSerie"] = "OTHER"
        with tempfile.TemporaryDirectory() as temporary:
            directory = create_sample_directory(Path(temporary))
            with self.assertRaises(ValueError):
                self.collect(directory, payloads)
            capture = directory / "banxico_SF43718_observations.json"
            self.assertEqual(json.loads(capture.read_text(encoding="utf-8"))["payload"], payloads[3])
            self.assertEqual(len(list(directory.glob("*_metadata.json"))), 4)
            self.assertFalse((directory / "profile.json").exists())

    def test_connection_failure_keeps_previous_captures_and_does_not_claim_completion(self):
        payloads = [observations_payload(SERIES[0]), RuntimeError("FRED: fixture connection failure")]
        with tempfile.TemporaryDirectory() as temporary:
            directory = create_sample_directory(Path(temporary))
            with self.assertRaises(RuntimeError):
                self.collect(directory, payloads)
            self.assertTrue((directory / "fred_PMAIZMTUSDM_observations.json").exists())
            self.assertFalse((directory / "fred_PWHEAMTUSDM_observations.json").exists())
            self.assertFalse((directory / "profile.json").exists())

    def test_new_runs_and_exclusive_writes_preserve_earlier_captures(self):
        with tempfile.TemporaryDirectory() as temporary:
            first = create_sample_directory(Path(temporary))
            second = create_sample_directory(Path(temporary))
            self.assertNotEqual(first, second)
            path = save_capture(first, SERIES[0], "metadata", {"title": "original"})
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                save_capture(first, SERIES[0], "metadata", {"title": "replacement"})
            self.assertEqual(path.read_bytes(), before)
            # Un documento no serializable tampoco deja un archivo vacío.
            invalid_path = second / "invalid.json"
            with self.assertRaises(TypeError):
                write_json(invalid_path, {"unsupported": object()})
            self.assertFalse(invalid_path.exists())

    def test_cli_returns_a_failure_status_when_the_profile_contains_issues(self):
        # Aquí probamos la decisión de salida del comando; el flujo completo
        # con contratos y archivos ya se ejercita en los escenarios anteriores.
        with tempfile.TemporaryDirectory() as temporary:
            for has_issues in (False, True):
                report = {"sample_month": "2026-09", "has_issues": has_issues, "profiles": []}
                with self.subTest(has_issues=has_issues):
                    with patch("grain_pipeline.extraction.sample.load_credentials", return_value=CREDENTIALS):
                        # El reloj es irrelevante aquí. Una zona estándar evita
                        # que este caso dependa de instalar la base IANA real.
                        with patch("grain_pipeline.extraction.sample.ZoneInfo", return_value=timezone.utc):
                            with patch("grain_pipeline.extraction.sample.collect_sample", return_value=report):
                                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                                    status = main(["--output-dir", temporary])
                    self.assertEqual(status, int(has_issues))
