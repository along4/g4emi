"""Full end-to-end example: YAML -> simulation -> photon transport."""

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
from src.optics.OpticalTransport import resolve_transport_paths, transport_from_sim_config  # noqa: E402
from src.runner import run  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run full pipeline from SimConfig YAML: write macro, run g4emi, "
            "and transport photons to the intensifier plane."
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
        "--beam-on",
        type=int,
        default=None,
        help="Optional override for simulation numberOfParticles.",
    )
    parser.add_argument(
        "--g4emi-binary",
        type=str,
        default=None,
        help="Optional override for `runner.binary` from the YAML config.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned commands/paths without running simulation or transport.",
    )
    parser.add_argument(
        "--no-overwrite-transport",
        action="store_true",
        help="Fail if the transport output HDF5 already exists.",
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
    if args.g4emi_binary is not None:
        config.runner.binary = args.g4emi_binary
    log_path = configure_run_logger(config)
    logger = get_logger()

    write_macro(
        config,
        include_output=True,
        include_run_initialize=True,
        overwrite=True,
    )
    paths = resolve_run_environment_paths(config)
    macro_path = paths.macro_file.resolve()
    simulated_hdf5 = (paths.simulated_photons / simulated_output_filename(config)).resolve()
    transported_hdf5 = resolve_transport_paths(config).output_hdf5.resolve()

    logger.info(f"Run log: {log_path}")
    logger.info(f"YAML: {yaml_path}")
    logger.info(f"Macro: {macro_path}")
    logger.info(f"Simulation binary: {config.runner.binary}")
    logger.info(f"Expected simulated HDF5: {simulated_hdf5}")
    logger.info(f"Expected transport HDF5: {transported_hdf5}")

    completed = run(config, dry_run=args.dry_run)

    if completed is None:
        logger.info("Dry run requested; skipping simulation and transport.")
        return

    if not simulated_hdf5.exists():
        raise FileNotFoundError(
            "Simulation finished but expected HDF5 was not found: "
            f"{simulated_hdf5}"
        )

    summary = transport_from_sim_config(
        config,
        input_hdf5_path=simulated_hdf5,
        output_hdf5_path=transported_hdf5,
        overwrite=not args.no_overwrite_transport,
    )
    logger.info("Transport finished.")
    logger.info(f"Transport engine: {summary.ray_engine}")
    logger.info(
        "Photons: "
        f"total={summary.total_photons}, "
        f"transported={summary.transported_photons}, "
        f"missed={summary.missed_photons}"
    )
    logger.info(f"Transport output: {summary.output_hdf5}")


if __name__ == "__main__":
    main()
