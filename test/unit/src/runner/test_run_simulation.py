"""Unit tests for `src.runner.runSimulation`."""

from __future__ import annotations

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
        cls.run_simulation = staticmethod(run)

    def _config_for_tmp(self, tmp_path: Path):
        config = self.default_sim_config()
        config.metadata.run_environment.working_directory = tmp_path.as_posix()
        config.metadata.run_environment.simulation_run_id = "runner_test"
        return config

    def test_run_dry_run_skips_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self._config_for_tmp(tmp_path)
            paths = self.resolve_run_environment_paths(config)
            paths.macro.mkdir(parents=True, exist_ok=True)
            paths.macro_file.write_text("/run/initialize\n", encoding="utf-8")

            with patch("src.runner.runSimulation.subprocess.run") as run_mock:
                result = self.run_simulation(config, dry_run=True)

            self.assertIsNone(result)
            run_mock.assert_not_called()

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

            def _run_side_effect(command, **kwargs):
                output_hdf5.write_text("ok\n", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0)

            with patch(
                "src.runner.runSimulation.subprocess.run",
                side_effect=_run_side_effect,
            ) as run_mock:
                completed = self.run_simulation(config)

            self.assertIsInstance(completed, subprocess.CompletedProcess)
            run_mock.assert_called_once_with(
                ["pixi", "run", "g4emi", str(paths.macro_file.resolve())],
                check=True,
                text=True,
            )

    def test_run_rejects_missing_macro(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self._config_for_tmp(tmp_path)

            with patch("src.runner.runSimulation.subprocess.run") as run_mock:
                with self.assertRaises(FileNotFoundError):
                    self.run_simulation(config)

            run_mock.assert_not_called()

    def test_run_requires_output_when_verification_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self._config_for_tmp(tmp_path)
            paths = self.resolve_run_environment_paths(config)
            paths.macro.mkdir(parents=True, exist_ok=True)
            paths.macro_file.write_text("/run/initialize\n", encoding="utf-8")

            with patch(
                "src.runner.runSimulation.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    [config.runner.binary, str(paths.macro_file.resolve())],
                    0,
                ),
            ):
                with self.assertRaises(FileNotFoundError):
                    self.run_simulation(config)

    def test_run_skips_output_check_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self._config_for_tmp(tmp_path)
            config.runner.verify_output = False
            paths = self.resolve_run_environment_paths(config)
            paths.macro.mkdir(parents=True, exist_ok=True)
            paths.macro_file.write_text("/run/initialize\n", encoding="utf-8")

            with patch(
                "src.runner.runSimulation.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    [config.runner.binary, str(paths.macro_file.resolve())],
                    0,
                ),
            ) as run_mock:
                completed = self.run_simulation(config)

            self.assertEqual(completed.returncode, 0)
            run_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
