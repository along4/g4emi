"""Generate an overlaid secondary-track-length histogram from HDF5 output."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure repository root is importable when run directly.
sys.path.append(str(Path(__file__).resolve().parents[2]))

from analysis.hdf5Analyzer import (  # noqa: E402
    secondary_track_lengths_by_species_mm,
    secondary_track_lengths_overlay_to_histogram,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Overlay secondary-track-length histograms by species from a g4emi HDF5 file."
        )
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
        help=(
            "Directory for the output PNG "
            "(default: <run_root>/plots when inferable, else <input_dir>/plots)."
        ),
    )
    parser.add_argument(
        "--species",
        nargs="+",
        default=None,
        help="Optional subset of secondary species to include in the overlay.",
    )
    parser.add_argument(
        "--bins",
        type=int,
        default=128,
        help="Number of histogram bins (default: 128).",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.45,
        help="Fill opacity for overlaid distributions, in (0, 1] (default: 0.45).",
    )
    parser.add_argument(
        "--linear-y",
        action="store_true",
        help="Use a linear y-axis instead of the default logarithmic axis.",
    )
    parser.add_argument(
        "--x-max",
        type=float,
        default=None,
        help="Optional maximum x-axis value in mm to clamp long track-length tails.",
    )
    return parser.parse_args()


def _default_output_dir_from_input(hdf5_path: Path) -> Path:
    stage_dir_names = {"simulatedPhotons", "transportedPhotons"}
    if hdf5_path.parent.name in stage_dir_names:
        return hdf5_path.parent.parent / "plots"
    return hdf5_path.parent / "plots"


def main() -> None:
    args = _parse_args()
    hdf5_path = args.hdf5_path.expanduser().resolve()
    if not hdf5_path.exists():
        raise FileNotFoundError(f"Input HDF5 file not found: {hdf5_path}")

    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir is not None
        else _default_output_dir_from_input(hdf5_path).resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "secondary_track_lengths_overlay.png"

    grouped_lengths = secondary_track_lengths_by_species_mm(
        hdf5_path,
        secondary_species=args.species,
    )
    secondary_track_lengths_overlay_to_histogram(
        hdf5_path,
        bins=args.bins,
        secondary_species=args.species,
        alpha=args.alpha,
        log_scale=not args.linear_y,
        x_max=args.x_max,
        output_path=output_path,
    )

    print(f"Input HDF5: {hdf5_path}")
    print(f"Wrote image: {output_path}")
    print("Included species:")
    for species, lengths_mm in grouped_lengths.items():
        print(f"  - {species}: {len(lengths_mm)} tracks")


if __name__ == "__main__":
    main()
