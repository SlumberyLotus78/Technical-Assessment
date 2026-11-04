"""Contratos de distribucion y del ejecutor programado; sin APIs ni base del proyecto."""

from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest
from unittest.mock import Mock, patch

from app.launcher import main as dashboard_main
from grain_pipeline.orchestration.scheduled import execute_scheduled


class ScheduledExecutionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="grain automation ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.env_file = self.root / "fixture.env"
        self.env_file.write_text("FRED_API_KEY=private-fixture-not-a-real-key", encoding="utf-8")

    def execute(self, **kwargs):
        return execute_scheduled(self.env_file, self.root / "bronze", self.root / "logs",
                                  review_months=kwargs.pop("review_months", 3),
                                  timeout_seconds=kwargs.pop("timeout_seconds", 60), **kwargs)

    def test_installed_child_is_isolated_and_only_invokes_incremental_with_absolute_paths(self):
        with patch("grain_pipeline.orchestration.scheduled.subprocess.run", return_value=Mock(returncode=0)) as child:
            first, second = self.execute(), self.execute()
        command = child.call_args.args[0]
        self.assertIn("-I", command)
        self.assertIn("grain_pipeline.orchestration.incremental", command)
        self.assertNotIn("historical", " ".join(command))
        self.assertIn(str(self.env_file.resolve()), command)
        self.assertEqual(first["exit_code"], 0)
        self.assertNotEqual(first["execution_id"], second["execution_id"])
        reports = list((self.root / "logs").glob("*.json"))
        self.assertEqual(len(reports), 2)
        self.assertNotIn("private-fixture", "".join(file.read_text(encoding="utf-8") for file in reports))

    def test_child_exit_code_is_propagated_and_logs_are_retained(self):
        def child(command, *, stdout, **kwargs):
            stdout.write("fixture controlled diagnostic\n")
            return Mock(returncode=7)
        with patch("grain_pipeline.orchestration.scheduled.subprocess.run", side_effect=child):
            result = self.execute()
        self.assertEqual((result["status"], result["exit_code"]), ("failed", 7))
        self.assertIn("controlled diagnostic", (self.root / "logs" / result["log_file"]).read_text(encoding="utf-8"))

    def test_timeout_and_launch_failure_do_not_expose_original_exception_details(self):
        for error, status, code in ((subprocess.TimeoutExpired("private-command", 60), "timeout", 124),
                                     (OSError("private-driver-detail"), "launch_failed", 1)):
            with patch("grain_pipeline.orchestration.scheduled.subprocess.run", side_effect=error):
                result = self.execute()
            self.assertEqual((result["status"], result["exit_code"]), (status, code))
            self.assertNotIn("private-", (self.root / "logs" / result["log_file"]).read_text(encoding="utf-8"))

    def test_readiness_mode_uses_only_the_state_command(self):
        with patch("grain_pipeline.orchestration.scheduled.subprocess.run", return_value=Mock(returncode=0)) as child:
            result = self.execute(check_only=True)
        self.assertIn("grain_pipeline.orchestration.state", child.call_args.args[0])
        self.assertNotIn("--review-months", child.call_args.args[0])
        self.assertEqual(result["operation"], "state")

    def test_invalid_bounds_and_missing_configuration_prevent_child_execution(self):
        with patch("grain_pipeline.orchestration.scheduled.subprocess.run") as child:
            for options in ({"review_months": 13}, {"timeout_seconds": 0}, {"timeout_seconds": 7201}):
                with self.assertRaises(ValueError):
                    self.execute(**options)
            self.env_file.unlink()
            with self.assertRaises(ValueError):
                self.execute()
        child.assert_not_called()

    def test_missing_dashboard_extra_and_invalid_port_are_controlled(self):
        with patch("app.launcher.find_spec", return_value=None), redirect_stderr(io.StringIO()) as output:
            self.assertEqual(dashboard_main([]), 1)
        self.assertIn("dashboard", output.getvalue())
        with redirect_stderr(io.StringIO()):
            self.assertEqual(dashboard_main(["--port", "70000"]), 1)


class DistributionContractTests(unittest.TestCase):
    def test_package_and_development_requirements_have_the_same_runtime_versions(self):
        root = Path(__file__).resolve().parents[1]
        metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        declared = set(metadata["project"]["dependencies"] + metadata["project"]["optional-dependencies"]["dashboard"])
        requirements = {line.strip() for line in (root / "requirements.txt").read_text(encoding="utf-8-sig").splitlines()
                        if line.strip() and not line.lstrip().startswith("#")}
        self.assertEqual(declared, requirements)
        self.assertNotIn("streamlit==1.66.1", metadata["project"]["dependencies"])
        for package, patterns in metadata["tool"]["setuptools"]["package-data"].items():
            directory = root.joinpath(*package.split("."))
            for pattern in patterns:
                self.assertTrue(list(directory.glob(pattern)))
