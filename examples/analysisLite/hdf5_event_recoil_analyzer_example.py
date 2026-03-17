"""Generate a 2D event-level recoil-path and photon-origin plot from HDF5."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure repository root is importable when run directly.
sys.path.append(str(Path(__file__).resolve().parents[2]))

from analysis.hdf5Analyzer import event_recoil_paths_to_image  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot recoil paths and linked photon-origin points for one gun_call_id."
        )
    )
    parser.add_argument(
        "hdf5_path",
        type=Path,
        help="Path to input HDF5 file (e.g. data/.../photon_optical_interface_hits_0000.h5).",
    )
    parser.add_argument(
        "gun_call_id",
        type=int,
        help="Event ID (`gun_call_id`) to visualize.",
    )
    parser.add_argument(
        "--plane",
        choices=("xy", "xz", "yz"),
        default="xy",
        help="2D projection plane for the real-space view (default: xy).",
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
    output_path = output_dir / f"event_{args.gun_call_id}_{args.plane}_recoil_paths.png"

    event_recoil_paths_to_image(
        hdf5_path,
        args.gun_call_id,
        plane=args.plane,
        output_path=output_path,
    )

    print(f"Input HDF5: {hdf5_path}")
    print(f"gun_call_id: {args.gun_call_id}")
    print(f"Plane: {args.plane}")
    print(f"Wrote image: {output_path}")


if __name__ == "__main__":
    main()
