"""Unit tests for `src.runner.runSimulation`."""

from __future__ import annotations

import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


def _repo_root() -> Path:
    """Resolve repository root by searching parent directories."""

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src").is_dir() and (parent / "pixi.toml").is_file():
            return parent
    raise RuntimeError("Could not resolve repository root from test path.")


sys.path.insert(0, str(_repo_root()))


class RunSimulationTests(unittest.TestCase):
    """Validate runner launch behavior against resolved run artifacts."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from src.config.ConfigIO import DEFAULT_OUTPUT_FILENAME_BASE, resolve_run_environment_paths
            from src.config.SimConfig import default_sim_config
            from src.runner import run
            from src.runner.runSimulation import _parse_simulated_events
        except ModuleNotFoundError as exc:
            missing = (getattr(exc, "name", "") or "").lower()
            if missing in {"pydantic", "loguru"}:
                raise unittest.SkipTest(
                    f"Missing dependency for runner tests: {exc}. "
                    "Run in the project environment (for example: pixi run test-python)."
                ) from exc
            raise
        cls.DEFAULT_OUTPUT_FILENAME_BASE = DEFAULT_OUTPUT_FILENAME_BASE
        cls.default_sim_config = staticmethod(default_sim_config)
        cls.resolve_run_environment_paths = staticmethod(resolve_run_environment_paths)
        cls.parse_simulated_events = staticmethod(_parse_simulated_events)
        cls.run_simulation = staticmethod(run)

    class _FakeProcess:
        def __init__(self, lines: list[str], returncode: int = 0):
            self.stdout = io.StringIO("".join(lines))
            self.returncode = returncode

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            self.stdout.close()
            return False

        def wait(self) -> int:
            return self.returncode

    def _config_for_tmp(self, tmp_path: Path):
        config = self.default_sim_config()
        config.metadata.run_environment.working_directory = tmp_path.as_posix()
        config.metadata.run_environment.simulation_run_id = "runner_test"
        return config

    def test_parse_simulated_events_extracts_aggregate_count(self) -> None:
        self.assertEqual(
            self.parse_simulated_events("G4WT10 > Simulated 3000 events\n"),
            3000,
        )
        self.assertIsNone(
            self.parse_simulated_events(
                "G4WT9 > --> Event 6000 starts with initial seeds (1,2).\n"
            )
        )

    def test_run_dry_run_skips_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self._config_for_tmp(tmp_path)
            paths = self.resolve_run_environment_paths(config)
            paths.macro.mkdir(parents=True, exist_ok=True)
            paths.macro_file.write_text("/run/initialize\n", encoding="utf-8")

            with patch("src.runner.runSimulation.subprocess.Popen") as popen_mock:
                result = self.run_simulation(config, dry_run=True)

            self.assertIsNone(result)
            popen_mock.assert_not_called()

    def test_run_uses_binary_from_config_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self._config_for_tmp(tmp_path)
            config.runner.binary = "pixi run g4emi"
            paths = self.resolve_run_environment_paths(config)
            paths.macro.mkdir(parents=True, exist_ok=True)
            paths.simulated_photons.mkdir(parents=True, exist_ok=True)
            paths.macro_file.write_text("/run/initialize\n", encoding="utf-8")
            output_hdf5 = paths.simulated_photons / f"{self.DEFAULT_OUTPUT_FILENAME_BASE}.h5"
            expected_log_path = paths.log / "runLog.txt"
            output_hdf5.parent.mkdir(parents=True, exist_ok=True)
            output_hdf5.write_text("ok\n", encoding="utf-8")

            with patch(
                "src.runner.runSimulation.subprocess.Popen",
                return_value=self._FakeProcess(
                    ["G4WT10 > Simulated 10000 events\n"],
                    returncode=0,
                ),
            ) as popen_mock, patch(
                "src.runner.runSimulation.sys.stderr",
                new=io.StringIO(),
            ):
                completed = self.run_simulation(config)

            self.assertIsInstance(completed, subprocess.CompletedProcess)
            popen_mock.assert_called_once_with(
                ["pixi", "run", "g4emi", str(paths.macro_file.resolve())],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self.assertIn(
                "Simulated 10000 events",
                expected_log_path.read_text(encoding="utf-8"),
            )

    def test_run_suppresses_terminal_progress_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self._config_for_tmp(tmp_path)
            config.runner.show_progress = False
            paths = self.resolve_run_environment_paths(config)
            paths.macro.mkdir(parents=True, exist_ok=True)
            paths.simulated_photons.mkdir(parents=True, exist_ok=True)
            paths.macro_file.write_text("/run/initialize\n", encoding="utf-8")
            output_hdf5 = paths.simulated_photons / f"{self.DEFAULT_OUTPUT_FILENAME_BASE}.h5"
            output_hdf5.write_text("ok\n", encoding="utf-8")

            with patch(
                "src.runner.runSimulation.subprocess.Popen",
                return_value=self._FakeProcess(
                    ["G4WT10 > Simulated 10000 events\n"],
                    returncode=0,
                ),
            ), patch(
                "src.runner.runSimulation.sys.stderr",
                new=io.StringIO(),
            ) as stderr_capture:
                self.run_simulation(config)

            self.assertEqual(stderr_capture.getvalue(), "")

    def test_run_rejects_missing_macro(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self._config_for_tmp(tmp_path)

            with patch("src.runner.runSimulation.subprocess.Popen") as popen_mock:
                with self.assertRaises(FileNotFoundError):
                    self.run_simulation(config)

            popen_mock.assert_not_called()

    def test_run_requires_output_when_verification_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self._config_for_tmp(tmp_path)
            paths = self.resolve_run_environment_paths(config)
            paths.macro.mkdir(parents=True, exist_ok=True)
            paths.macro_file.write_text("/run/initialize\n", encoding="utf-8")

            with patch(
                "src.runner.runSimulation.subprocess.Popen",
                return_value=self._FakeProcess(
                    ["G4WT10 > Simulated 10000 events\n"],
                    returncode=0,
                ),
            ) as popen_mock, patch(
                "src.runner.runSimulation.sys.stderr",
                new=io.StringIO(),
            ):
                with self.assertRaises(FileNotFoundError):
                    self.run_simulation(config)

            popen_mock.assert_called_once()

    def test_run_skips_output_check_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self._config_for_tmp(tmp_path)
            config.runner.verify_output = False
            paths = self.resolve_run_environment_paths(config)
            paths.macro.mkdir(parents=True, exist_ok=True)
            paths.macro_file.write_text("/run/initialize\n", encoding="utf-8")

            with patch(
                "src.runner.runSimulation.subprocess.Popen",
                return_value=self._FakeProcess(
                    ["G4WT10 > Simulated 10000 events\n"],
                    returncode=0,
                ),
            ) as popen_mock, patch(
                "src.runner.runSimulation.sys.stderr",
                new=io.StringIO(),
            ):
                completed = self.run_simulation(config)

            self.assertEqual(completed.returncode, 0)
            popen_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
