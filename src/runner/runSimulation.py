"""Thin simulation launcher built on validated `SimConfig`."""

from __future__ import annotations

from pathlib import Path
import re
import shlex
import subprocess
import sys

try:
    from src.common.logger import get_logger, log_stage, resolve_run_log_path
    from src.config.ConfigIO import prepare_simulation_run
    from src.config.ConfigIO import (
        resolve_run_environment_paths,
        simulated_output_filename,
    )
    from src.config.SimConfig import SimConfig
except ModuleNotFoundError:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from src.common.logger import get_logger, log_stage, resolve_run_log_path
    from src.config.ConfigIO import prepare_simulation_run
    from src.config.ConfigIO import (
        resolve_run_environment_paths,
        simulated_output_filename,
    )
    from src.config.SimConfig import SimConfig


_SIMULATED_EVENTS_PATTERN = re.compile(r"Simulated\s+(\d+)\s+events\b")


def _simulation_command(config: SimConfig, macro_path: Path) -> list[str]:
    """Build subprocess command tokens from `config.runner.binary` + macro."""

    try:
        tokens = shlex.split(config.runner.binary)
    except ValueError as exc:
        raise ValueError(
            f"Could not parse `runner.binary` into command tokens: {exc}"
        ) from exc
    if not tokens:
        raise ValueError("`runner.binary` did not resolve to an executable command.")
    return [*tokens, str(macro_path)]


def _simulation_total_events(config: SimConfig) -> int | None:
    """Return total configured events for progress display, if available."""

    if config.simulation is None:
        return None
    return config.simulation.number_of_particles


def _parse_simulated_events(line: str) -> int | None:
    """Extract aggregate simulated-event count from a Geant4 status line."""

    match = _SIMULATED_EVENTS_PATTERN.search(line)
    if match is None:
        return None
    return int(match.group(1))


def _write_progress(current: int, total: int) -> None:
    """Render a simple in-terminal simulation progress bar."""

    if total <= 0:
        return
    clamped = min(current, total)
    width = 30
    fraction = clamped / total
    filled = int(width * fraction)
    bar = f"[{'#' * filled}{'-' * (width - filled)}]"
    percent = int(fraction * 100)
    sys.stderr.write(
        f"\rSimulation {bar} {percent:3d}% ({clamped}/{total} events)"
    )
    sys.stderr.flush()
    if clamped >= total:
        sys.stderr.write("\n")
        sys.stderr.flush()


def run(
    config: SimConfig,
    *,
    dry_run: bool = False,
    log_filename: str | Path | None = None,
) -> subprocess.CompletedProcess[str] | None:
    """Launch a simulation from validated config.

    Preconditions:
    - the macro has already been written to the canonical macro path
    - any desired logging has already been configured by the caller

    Returns the raw subprocess result when executed, or ``None`` for dry runs.
    """

    run_paths = resolve_run_environment_paths(config)
    macro_path = run_paths.macro_file.resolve()
    output_hdf5 = (run_paths.simulated_photons / simulated_output_filename(config)).resolve()

    if not macro_path.exists():
        raise FileNotFoundError(
            "Expected generated macro at "
            f"{macro_path}. Write the macro before calling `run(config)`."
        )
    if macro_path.is_dir():
        raise IsADirectoryError(
            "Resolved macro path is a directory, expected a file: "
            f"{macro_path}"
        )

    # Resolve the canonical log path for consistency with caller reporting.
    log_path = resolve_run_log_path(config)
    command = _simulation_command(config, macro_path)
    total_events = (
        _simulation_total_events(config) if config.runner.show_progress else None
    )

    logger = get_logger()
    if dry_run:
        return None

    last_progress = 0
    displayed_progress = False
    if log_filename is not None:
        log_path = Path(log_filename)
    logger.info(f"[simulation] Command: {shlex.join(command)}")
    logger.info(f"[simulation] Output HDF5: {output_hdf5}")
    with log_stage("simulation"):
        with log_path.open("a", encoding="utf-8") as log_file:
            with subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            ) as process:
                if process.stdout is None:
                    raise RuntimeError("Simulation process did not expose a stdout stream.")

                for line in process.stdout:
                    log_file.write(line)
                    log_file.flush()

                    if total_events is None:
                        continue
                    progress = _parse_simulated_events(line)
                    if progress is None or progress < last_progress:
                        continue
                    last_progress = progress
                    displayed_progress = True
                    _write_progress(progress, total_events)

                return_code = process.wait()

    if displayed_progress and total_events is not None and last_progress < total_events:
        sys.stderr.write("\n")
        sys.stderr.flush()
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, command)

    completed = subprocess.CompletedProcess(command, return_code)
    if config.runner.verify_output and not output_hdf5.exists():
        raise FileNotFoundError(
            "Simulation finished but expected HDF5 was not found: "
            f"{output_hdf5}"
        )
    return completed


def run_simulation(
    config: SimConfig,
    *,
    dry_run: bool = False,
    log_filename: str | Path | None = None,
) -> subprocess.CompletedProcess[str] | None:
    """Prepare and launch one simulation from validated config."""

    prepare_simulation_run(config)
    completed = run(config, dry_run=dry_run, log_filename=log_filename)
    if log_filename is not None:
        logger = get_logger(filename=str(log_filename))
    else:
        logger = get_logger()
    if completed is None:
        logger.info("Dry run requested; skipping g4emi launch.")
        return None
    logger.info("Simulation finished.")
    return completed
