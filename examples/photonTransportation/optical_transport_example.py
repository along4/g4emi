"""Run SimConfig-driven optical transport from simulation HDF5 output."""

from __future__ import annotations

from pathlib import Path
import argparse
import sys

# Ensure repository root is importable when this file is run directly.
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.common.logger import configure_run_logger, get_logger  # noqa: E402
from src.config.ConfigIO import from_yaml  # noqa: E402
from src.optics.OpticalTransport import transport_from_sim_config  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Transport /photons optical-interface hits through the primary lens "
            "defined in SimConfig and write a secondary transport HDF5."
        )
    )
    parser.add_argument(
        "yaml_path",
        type=Path,
        help="Path to SimConfig YAML used for run-environment and lens selection.",
    )
    parser.add_argument(
        "--input-hdf5",
        type=Path,
        default=None,
        help="Optional explicit input HDF5 path (defaults to simulatedPhotons stage).",
    )
    parser.add_argument(
        "--output-hdf5",
        type=Path,
        default=None,
        help="Optional explicit output HDF5 path (defaults to transportedPhotons stage).",
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Fail when output file already exists.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    yaml_path = args.yaml_path.expanduser().resolve()
    if not yaml_path.exists():
        raise FileNotFoundError(f"SimConfig YAML not found: {yaml_path}")

    config = from_yaml(yaml_path)
    log_path = configure_run_logger(config)
    logger = get_logger()
    summary = transport_from_sim_config(
        config,
        input_hdf5_path=args.input_hdf5,
        output_hdf5_path=args.output_hdf5,
        overwrite=not args.no_overwrite,
    )

    logger.info(f"Run log: {log_path}")
    logger.info(f"YAML: {yaml_path}")
    logger.info(f"Input HDF5: {summary.input_hdf5}")
    logger.info(f"Output HDF5: {summary.output_hdf5}")
    logger.info(f"Lens: {summary.lens_name} ({summary.lens_zmx_path})")
    logger.info(f"Ray engine: {summary.ray_engine}")
    logger.info(
        "Photons: "
        f"total={summary.total_photons}, "
        f"transported={summary.transported_photons}, "
        f"missed={summary.missed_photons}"
    )


if __name__ == "__main__":
    main()
