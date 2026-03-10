"""Thin simulation launcher built on validated `SimConfig`."""

from __future__ import annotations

from pathlib import Path
import shlex
import subprocess
import sys

try:
    from src.common.logger import resolve_run_log_path
    from src.config.ConfigIO import (
        DEFAULT_OUTPUT_FILENAME_BASE,
        resolve_run_environment_paths,
    )
    from src.config.SimConfig import SimConfig
except ModuleNotFoundError:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from src.common.logger import resolve_run_log_path
    from src.config.ConfigIO import (
        DEFAULT_OUTPUT_FILENAME_BASE,
        resolve_run_environment_paths,
    )
    from src.config.SimConfig import SimConfig


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


def run(
    config: SimConfig,
    *,
    dry_run: bool = False,
) -> subprocess.CompletedProcess[str] | None:
    """Launch a simulation from validated config.

    Preconditions:
    - the macro has already been written to the canonical macro path
    - any desired logging has already been configured by the caller

    Returns the raw subprocess result when executed, or ``None`` for dry runs.
    """

    run_paths = resolve_run_environment_paths(config)
    macro_path = run_paths.macro_file.resolve()
    output_hdf5 = (
        run_paths.simulated_photons / f"{DEFAULT_OUTPUT_FILENAME_BASE}.h5"
    ).resolve()

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
    resolve_run_log_path(config)
    command = _simulation_command(config, macro_path)

    if dry_run:
        return None

    completed = subprocess.run(command, check=True, text=True)
    if config.runner.verify_output and not output_hdf5.exists():
        raise FileNotFoundError(
            "Simulation finished but expected HDF5 was not found: "
            f"{output_hdf5}"
        )
    return completed
