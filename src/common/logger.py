"""Shared Python run logging backed by loguru."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from src.config.SimConfig import SimConfig


DEFAULT_RUN_LOG_FILENAME = "runLog.txt"
DEFAULT_SCREEN_LEVEL = "INFO"
DEFAULT_FILE_LEVEL = "DEBUG"
_SCREEN_FORMAT = "<level>{level: <8}</level> | {message}"
_FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
_RUN_LOGGER_CONFIGURED = False
_RUN_LOG_PATH: Path | None = None
_RUN_SCREEN_HANDLER_ID: int | None = None
_RUN_FILE_HANDLER_ID: int | None = None


def _require_loguru():
    """Import loguru lazily with a project-specific install hint."""

    try:
        from loguru import logger
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency availability varies
        raise ModuleNotFoundError(
            "loguru is required for Python run logging. "
            "Install project dependencies (for example: pixi install)."
        ) from exc
    return logger


def resolve_run_log_path(
    config: "SimConfig",
    *,
    filename: str = DEFAULT_RUN_LOG_FILENAME,
) -> Path:
    """Resolve the canonical run log path under the configured logs directory."""

    try:
        from src.config.ConfigIO import resolve_run_environment_paths
    except ModuleNotFoundError:
        sys.path.append(str(Path(__file__).resolve().parents[2]))
        from src.config.ConfigIO import resolve_run_environment_paths

    run_paths = resolve_run_environment_paths(config)
    run_paths.log.mkdir(parents=True, exist_ok=True)
    return (run_paths.log / filename).resolve()


def configure_run_logger(
    config: "SimConfig",
    *,
    screen_level: str = DEFAULT_SCREEN_LEVEL,
    file_level: str = DEFAULT_FILE_LEVEL,
    screen_sink: TextIO | None = None,
    filename: str = DEFAULT_RUN_LOG_FILENAME,
) -> Path:
    """Configure terminal and file sinks for the current run."""

    global _RUN_FILE_HANDLER_ID, _RUN_LOGGER_CONFIGURED, _RUN_LOG_PATH, _RUN_SCREEN_HANDLER_ID

    logger = _require_loguru()
    log_path = resolve_run_log_path(config, filename=filename)
    sink = sys.stderr if screen_sink is None else screen_sink

    _remove_owned_handlers(logger)
    _RUN_SCREEN_HANDLER_ID = logger.add(
        sink,
        level=screen_level,
        format=_SCREEN_FORMAT,
        colorize=bool(getattr(sink, "isatty", lambda: False)()),
        backtrace=False,
        diagnose=False,
        enqueue=False,
    )
    _RUN_FILE_HANDLER_ID = logger.add(
        log_path,
        level=file_level,
        format=_FILE_FORMAT,
        mode="w",
        encoding="utf-8",
        backtrace=False,
        diagnose=False,
        enqueue=False,
    )
    _RUN_LOGGER_CONFIGURED = True
    _RUN_LOG_PATH = log_path
    return log_path


def ensure_run_logger(
    config: "SimConfig",
    *,
    screen_level: str = DEFAULT_SCREEN_LEVEL,
    file_level: str = DEFAULT_FILE_LEVEL,
    screen_sink: TextIO | None = None,
    filename: str = DEFAULT_RUN_LOG_FILENAME,
) -> Path:
    """Configure run logging only when it is absent or targets a new run log."""

    global _RUN_LOG_PATH

    log_path = resolve_run_log_path(config, filename=filename)
    if _RUN_LOGGER_CONFIGURED and _RUN_LOG_PATH == log_path:
        return log_path
    return configure_run_logger(
        config,
        screen_level=screen_level,
        file_level=file_level,
        screen_sink=screen_sink,
        filename=filename,
    )


def is_run_logger_configured() -> bool:
    """Return whether the shared run logger has been configured."""

    return _RUN_LOGGER_CONFIGURED


def get_logger():
    """Return the shared loguru logger."""

    return _require_loguru()


def _remove_owned_handlers(logger: object) -> None:
    """Remove only the handler IDs created by this module."""

    global _RUN_FILE_HANDLER_ID, _RUN_SCREEN_HANDLER_ID

    for handler_id_name in ("_RUN_SCREEN_HANDLER_ID", "_RUN_FILE_HANDLER_ID"):
        handler_id = globals()[handler_id_name]
        if handler_id is None:
            continue
        try:
            logger.remove(handler_id)
        except ValueError:
            pass
        globals()[handler_id_name] = None
