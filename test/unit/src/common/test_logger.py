"""Unit tests for shared Python run logging."""

from __future__ import annotations

import io
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


def _repo_root() -> Path:
    """Resolve repository root by searching parent directories."""

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src").is_dir() and (parent / "pixi.toml").is_file():
            return parent
    raise RuntimeError("Could not resolve repository root from test path.")


sys.path.insert(0, str(_repo_root()))


class RunLoggerTests(unittest.TestCase):
    """Validate canonical run log placement and severity routing."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.loguru_available = importlib.util.find_spec("loguru") is not None
        if not cls.loguru_available:
            raise unittest.SkipTest(
                "Missing dependency for run-logger tests: loguru. "
                "Refresh the project environment and rerun tests."
            )

        try:
            from src.common.logger import (
                configure_run_logger,
                get_logger,
                resolve_run_log_path,
            )
            from src.config.SimConfig import default_sim_config
        except ModuleNotFoundError as exc:
            missing = (getattr(exc, "name", "") or "").lower()
            if missing in {"loguru", "pydantic"}:
                raise unittest.SkipTest(
                    f"Missing dependency for run-logger tests: {exc}. "
                    "Run in the project environment (for example: pixi install)."
                ) from exc
            raise

        cls.configure_run_logger = staticmethod(configure_run_logger)
        cls.get_logger = staticmethod(get_logger)
        cls.resolve_run_log_path = staticmethod(resolve_run_log_path)
        cls.default_sim_config = staticmethod(default_sim_config)

    def _build_config(self, working_directory: Path) -> object:
        config = self.default_sim_config()
        config.metadata.run_environment.working_directory = str(working_directory)
        config.metadata.run_environment.simulation_run_id = "logger_unit_test"
        config.metadata.run_environment.log_directory = "logs"
        return config

    def test_resolve_run_log_path_uses_run_logs_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._build_config(Path(temp_dir))

            log_path = self.resolve_run_log_path(config)

            self.assertEqual(
                log_path,
                (Path(temp_dir) / "logger_unit_test" / "logs" / "runLog.txt").resolve(),
            )
            self.assertTrue(log_path.parent.is_dir())

    def test_configured_logger_writes_minor_messages_only_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._build_config(Path(temp_dir))
            screen_capture = io.StringIO()

            log_path = self.configure_run_logger(config, screen_sink=screen_capture)
            logger = self.get_logger()
            logger.debug("minor detail")
            logger.info("major info")
            logger.warning("major warning")

            screen_output = screen_capture.getvalue()
            file_output = log_path.read_text(encoding="utf-8")

            self.assertNotIn("minor detail", screen_output)
            self.assertIn("major info", screen_output)
            self.assertIn("major warning", screen_output)
            self.assertIn("minor detail", file_output)
            self.assertIn("major info", file_output)
            self.assertIn("major warning", file_output)

    def test_reconfigure_preserves_unrelated_loguru_handlers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._build_config(Path(temp_dir))
            logger = self.get_logger()
            external_capture = io.StringIO()
            external_handler_id = logger.add(
                external_capture,
                level="INFO",
                format="{message}",
            )
            try:
                self.configure_run_logger(config, screen_sink=io.StringIO())
                logger.info("first message")

                self.configure_run_logger(config, screen_sink=io.StringIO())
                logger.info("second message")

                external_output = external_capture.getvalue()
                self.assertIn("first message", external_output)
                self.assertIn("second message", external_output)
            finally:
                logger.remove(external_handler_id)

    def test_reconfigure_appends_to_existing_run_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._build_config(Path(temp_dir))
            logger = self.get_logger()

            log_path = self.configure_run_logger(config, screen_sink=io.StringIO())
            logger.info("simulation stage")

            self.configure_run_logger(config, screen_sink=io.StringIO())
            logger.info("transport stage")

            file_output = log_path.read_text(encoding="utf-8")
            self.assertIn("simulation stage", file_output)
            self.assertIn("transport stage", file_output)


if __name__ == "__main__":
    unittest.main()
