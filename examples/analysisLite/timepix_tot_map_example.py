"""Generate a Timepix integrated-ToT pixel map from a sensor HDF5 file."""

from __future__ import annotations

import argparse
from pathlib import Path

from matplotlib import pyplot as plt

from example_support import default_output_dir_from_input, ensure_repo_root_on_path  # noqa: E402

ensure_repo_root_on_path()
from analysis.spatial import timepix_tot_to_image  # noqa: E402


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for sensor-analysis input/output paths."""

    parser = argparse.ArgumentParser(
        description="Generate a Timepix integrated-ToT map from a sensor HDF5 file."
    )
    parser.add_argument(
        "hdf5_path",
        type=Path,
        help="Path to input sensor HDF5 file (e.g. data/.../sensor/timepix_hits_0000.h5).",
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
        "--show",
        action="store_true",
        help="Display the plot interactively instead of writing a PNG.",
    )
    return parser.parse_args()


def main() -> None:
    """Generate a Timepix integrated-ToT map from a sensor HDF5 file."""

    args = _parse_args()
    hdf5_path = args.hdf5_path.expanduser().resolve()
    if not hdf5_path.exists():
        raise FileNotFoundError(f"Input sensor HDF5 file not found: {hdf5_path}")

    output_dir = None
    if not args.show:
        output_dir = (
            args.output_dir.expanduser().resolve()
            if args.output_dir is not None
            else default_output_dir_from_input(hdf5_path).resolve()
        )
        output_dir.mkdir(parents=True, exist_ok=True)

    output_path = (
        None if output_dir is None else output_dir / "timepix_integrated_tot.png"
    )
    timepix_tot_to_image(
        hdf5_path,
        output_path=output_path,
        show=False,
    )

    print(f"Input sensor HDF5: {hdf5_path}")
    if args.show:
        print("Displaying plot interactively.")
        plt.show()
    else:
        print(f"Wrote image: {output_path}")


if __name__ == "__main__":
    main()
