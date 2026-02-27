"""Minimal example for the lightweight HDF5 analyzer.

This script demonstrates how to generate quick-look images from a simulation
HDF5 output file.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure repository root is importable when run directly.
sys.path.append(str(Path(__file__).resolve().parents[2]))

from analysis.hdf5Analyzer import (  # noqa: E402
    neutron_hits_to_image,
    optical_interface_photons_to_image,
    photon_exit_to_image,
    photon_origins_to_image,
)


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for input/output paths."""

    parser = argparse.ArgumentParser(
        description="Generate lightweight analyzer images from a g4emi HDF5 file."
    )
    parser.add_argument(
        "hdf5_path",
        type=Path,
        help="Path to input HDF5 file (e.g. data/.../photon_optical_interface_hits.h5).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for output PNGs (default: analysis/outputs).",
    )
    return parser.parse_args()


def main() -> None:
    """Generate four analyzer images from a sample HDF5 file."""

    args = _parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    hdf5_path = args.hdf5_path.expanduser().resolve()
    if not hdf5_path.exists():
        raise FileNotFoundError(f"Input HDF5 file not found: {hdf5_path}")

    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir is not None
        else repo_root / "analysis" / "outputs"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    neutron_png = output_dir / "neutron_hits.png"
    origins_png = output_dir / "photon_origins.png"
    exit_png = output_dir / "photon_exit.png"
    interface_png = output_dir / "optical_interface_photons.png"

    neutron_hits_to_image(hdf5_path, output_path=neutron_png)
    photon_origins_to_image(hdf5_path, output_path=origins_png)
    photon_exit_to_image(hdf5_path, output_path=exit_png)
    optical_interface_photons_to_image(hdf5_path, output_path=interface_png)

    print(f"Input HDF5: {hdf5_path}")
    print("Wrote images:")
    print(f"  - {neutron_png}")
    print(f"  - {origins_png}")
    print(f"  - {exit_png}")
    print(f"  - {interface_png}")


if __name__ == "__main__":
    main()
