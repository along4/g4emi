"""Shared Python run logging backed by loguru."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import re
import sys
import time
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from src.config.SimConfig import SimConfig


DEFAULT_RUN_LOG_FILENAME = "runLog.txt"
DEFAULT_SCREEN_LEVEL = "INFO"
DEFAULT_FILE_LEVEL = "DEBUG"
_SCREEN_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "{extra[stage_prefix]}{extra[message_body]}"
)
_FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
_STAGE_PREFIX_PATTERN = re.compile(
    r"^\[(setup|run|simulation|transport|intensifier|sensor)\]\s*"
)
_RUN_LOGGER_CONFIGURED = False
_RUN_LOG_PATH: Path | None = None
_RUN_SCREEN_HANDLER_ID: int | None = None
_RUN_FILE_HANDLER_ID: int | None = None
_RUN_LOGGER = None


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


def _stage_prefix_patcher(record: dict[str, object]) -> None:
    """Expose colored stage prefixes for the screen sink without changing files."""

    message = str(record["message"])
    match = _STAGE_PREFIX_PATTERN.match(message)
    if match is None:
        record["extra"]["stage_prefix"] = ""
        record["extra"]["message_body"] = message
        return
    stage_name = match.group(1)
    record["extra"]["stage_prefix"] = f"<blue>[{stage_name}]</blue> "
    record["extra"]["message_body"] = message[match.end() :]


def resolve_run_log_path(
    config: "SimConfig",
    *,
    filename: str | None = None,
) -> Path:
    """Resolve the canonical run log path under the configured logs directory."""

    try:
        from src.config.ConfigIO import resolve_run_environment_paths, run_log_filename
    except ModuleNotFoundError:
        sys.path.append(str(Path(__file__).resolve().parents[2]))
        from src.config.ConfigIO import resolve_run_environment_paths, run_log_filename

    run_paths = resolve_run_environment_paths(config)
    run_paths.log.mkdir(parents=True, exist_ok=True)
    target_filename = filename if filename is not None else run_log_filename(config)
    return (run_paths.log / target_filename).resolve()


def configure_run_logger(
    config: "SimConfig",
    *,
    screen_level: str = DEFAULT_SCREEN_LEVEL,
    file_level: str = DEFAULT_FILE_LEVEL,
    screen_sink: TextIO | None = None,
    filename: str | None = None,
) -> Path:
    """Configure terminal and file sinks for the current run."""

    global _RUN_FILE_HANDLER_ID, _RUN_LOGGER, _RUN_LOGGER_CONFIGURED, _RUN_LOG_PATH, _RUN_SCREEN_HANDLER_ID

    base_logger = _require_loguru()
    logger = base_logger.patch(_stage_prefix_patcher)
    log_path = resolve_run_log_path(config, filename=filename)
    sink = sys.stderr if screen_sink is None else screen_sink

    base_logger.remove()
    _RUN_SCREEN_HANDLER_ID = None
    _RUN_FILE_HANDLER_ID = None
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
        mode="a",
        encoding="utf-8",
        backtrace=False,
        diagnose=False,
        enqueue=False,
    )
    _RUN_LOGGER_CONFIGURED = True
    _RUN_LOG_PATH = log_path
    _RUN_LOGGER = logger
    return log_path


def ensure_run_logger(
    config: "SimConfig",
    *,
    screen_level: str = DEFAULT_SCREEN_LEVEL,
    file_level: str = DEFAULT_FILE_LEVEL,
    screen_sink: TextIO | None = None,
    filename: str | None = None,
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

    if _RUN_LOGGER is not None:
        return _RUN_LOGGER
    return _require_loguru().patch(_stage_prefix_patcher)


@contextmanager
def log_stage(stage_name: str):
    """Log a stage start/finish pair with elapsed wall time."""

    logger = get_logger()
    start_time = time.perf_counter()
    logger.info(f"[{stage_name}] Starting.")
    try:
        yield
    except Exception:
        elapsed_s = time.perf_counter() - start_time
        logger.exception(f"[{stage_name}] Failed after {elapsed_s:.2f} s.")
        raise
    elapsed_s = time.perf_counter() - start_time
    logger.info(f"[{stage_name}] Finished in {elapsed_s:.2f} s.")


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
