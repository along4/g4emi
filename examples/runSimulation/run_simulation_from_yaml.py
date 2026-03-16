"""Generate macro from YAML and run g4emi in one step."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure repository root is importable when this file is run directly.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from src.common.logger import configure_run_logger, get_logger  # noqa: E402
from src.config.ConfigIO import (  # noqa: E402
    from_yaml,
    resolve_run_environment_paths,
    simulated_output_filename,
    write_macro,
)
from src.config.SimConfig import SimulationConfig  # noqa: E402
from src.runner import run  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Load SimConfig YAML, generate macro, and run g4emi with that macro."
        )
    )
    parser.add_argument(
        "yaml_path",
        nargs="?",
        type=Path,
        default=REPO_ROOT / "examples" / "yamlFiles" / "CanonEF50mmf1p0L_example.yaml",
        help="SimConfig YAML path (default: Canon example under examples/yamlFiles).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate macro and print run command without launching g4emi.",
    )
    parser.add_argument(
        "--beam-on",
        type=int,
        default=None,
        help="Optional override for simulation numberOfParticles.",
    )
    return parser

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    yaml_path = args.yaml_path.expanduser().resolve()
    if not yaml_path.exists():
        raise FileNotFoundError(f"SimConfig YAML not found: {yaml_path}")

    config = from_yaml(yaml_path)
    if args.beam_on is not None:
        if args.beam_on <= 0:
            raise ValueError("--beam-on must be > 0.")
        if config.simulation is None:
            config.simulation = SimulationConfig(number_of_particles=args.beam_on)
        else:
            config.simulation.number_of_particles = args.beam_on
    log_path = configure_run_logger(config)
    logger = get_logger()

    write_macro(
        config,
        include_output=True,
        include_run_initialize=True,
    )
    paths = resolve_run_environment_paths(config)
    macro_path = paths.macro_file.resolve()
    output_hdf5 = (paths.simulated_photons / simulated_output_filename(config)).resolve()

    logger.info(f"Run log: {log_path}")
    logger.info(f"YAML: {yaml_path}")
    logger.info(f"Macro: {macro_path}")
    logger.info(f"Expected HDF5: {output_hdf5}")
    logger.info(f"Binary: {config.runner.binary}")

    completed = run(config, dry_run=args.dry_run)

    if completed is None:
        logger.info("Dry run requested; skipping g4emi launch.")
        return

    logger.info("Simulation finished.")


if __name__ == "__main__":
    main()
