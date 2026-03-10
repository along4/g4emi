"""Full end-to-end example: YAML -> simulation -> photon transport."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

# Ensure repository root is importable when this file is run directly.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from src.common.logger import configure_run_logger, get_logger  # noqa: E402
from src.config.ConfigIO import (  # noqa: E402
    DEFAULT_OUTPUT_FILENAME_BASE,
    from_yaml,
    resolve_run_environment_paths,
    write_macro,
)
from src.config.SimConfig import SimulationConfig  # noqa: E402
from src.optics.OpticalTransport import (  # noqa: E402
    DEFAULT_TRANSPORT_OUTPUT_FILENAME,
    transport_from_sim_config,
)


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
        default="g4emi",
        help="Executable name/path for Geant4 simulation binary (default: g4emi).",
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
    simulated_hdf5 = (paths.simulated_photons / f"{DEFAULT_OUTPUT_FILENAME_BASE}.h5").resolve()
    transported_hdf5 = (
        paths.transported_photons / DEFAULT_TRANSPORT_OUTPUT_FILENAME
    ).resolve()

    simulation_command = [args.g4emi_binary, str(macro_path)]

    logger.info(f"Run log: {log_path}")
    logger.info(f"YAML: {yaml_path}")
    logger.info(f"Macro: {macro_path}")
    logger.info(f"Simulation command: {' '.join(simulation_command)}")
    logger.info(f"Expected simulated HDF5: {simulated_hdf5}")
    logger.info(f"Expected transport HDF5: {transported_hdf5}")

    if args.dry_run:
        logger.info("Dry run requested; skipping simulation and transport.")
        return

    subprocess.run(simulation_command, check=True)
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
