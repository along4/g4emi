"""Minimal example for lightweight spatial analysis from simulation HDF5.

This script demonstrates how to generate quick-look images from a simulation
HDF5 output file.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from example_support import (  # noqa: E402
    default_output_dir_from_input,
    ensure_repo_root_on_path,
    infer_transport_hdf5_path,
)

ensure_repo_root_on_path()
from analysis.spatial import (  # noqa: E402
    intensifier_photons_to_image,
    neutron_hits_to_image,
    optical_interface_photons_to_image,
    photon_exit_to_image,
    photon_origins_to_image,
)


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for input/output paths."""

    parser = argparse.ArgumentParser(
        description="Generate lightweight spatial analysis images from a g4emi HDF5 file."
    )
    parser.add_argument(
        "hdf5_path",
        type=Path,
        help="Path to input HDF5 file (e.g. data/.../photon_optical_interface_hits_0000.h5).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory for output PNGs "
            "(default: <run_root>/plots when inferable, else <input_dir>/plots)."
        ),
    )
    parser.add_argument(
        "--transport-hdf5-path",
        type=Path,
        default=None,
        help=(
            "Optional transport HDF5 path containing /transported_photons. "
            "If omitted, tries sibling path "
            "data/<run>/transportedPhotons/photons_intensifier_hits_0000.h5."
        ),
    )
    parser.add_argument(
        "--sim-config-yaml",
        type=Path,
        default=None,
        help=(
            "Optional SimConfig YAML path used to set photon-origin/exit plot "
            "extents to scintillator XY size. If omitted, bounds are inferred "
            "from HDF5 data unless --xy-limits is provided."
        ),
    )
    parser.add_argument(
        "--xy-limits",
        nargs=4,
        type=float,
        metavar=("X_MIN", "X_MAX", "Y_MIN", "Y_MAX"),
        default=None,
        help=(
            "Explicit XY limits for photon origin/exit plots in mm. "
            "Takes precedence over --sim-config-yaml."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Generate five quick-look spatial analysis images from one HDF5 file."""

    args = _parse_args()
    hdf5_path = args.hdf5_path.expanduser().resolve()
    if not hdf5_path.exists():
        raise FileNotFoundError(f"Input HDF5 file not found: {hdf5_path}")

    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir is not None
        else default_output_dir_from_input(hdf5_path).resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    neutron_png = output_dir / "neutron_hits.png"
    origins_png = output_dir / "photon_origins.png"
    exit_png = output_dir / "photon_exit.png"
    interface_png = output_dir / "optical_interface_photons.png"
    intensifier_png = output_dir / "photons_intensifier_hits.png"

    transport_hdf5_path = (
        args.transport_hdf5_path.expanduser().resolve()
        if args.transport_hdf5_path is not None
        else infer_transport_hdf5_path(hdf5_path)
    )
    sim_config_yaml_path = (
        args.sim_config_yaml.expanduser().resolve()
        if args.sim_config_yaml is not None
        else None
    )
    if sim_config_yaml_path is not None and not sim_config_yaml_path.exists():
        raise FileNotFoundError(f"SimConfig YAML not found: {sim_config_yaml_path}")

    xy_range_override = None
    if args.xy_limits is not None:
        x_min, x_max, y_min, y_max = [float(value) for value in args.xy_limits]
        if not x_min < x_max:
            raise ValueError("--xy-limits requires X_MIN < X_MAX.")
        if not y_min < y_max:
            raise ValueError("--xy-limits requires Y_MIN < Y_MAX.")
        xy_range_override = (
            (x_min, x_max),
            (y_min, y_max),
        )

    neutron_hits_to_image(hdf5_path, output_path=neutron_png)
    photon_origins_to_image(
        hdf5_path,
        output_path=origins_png,
        use_scintillator_extent=(sim_config_yaml_path is not None),
        sim_config_yaml_path=sim_config_yaml_path,
        xy_range_override=xy_range_override,
    )
    photon_exit_to_image(
        hdf5_path,
        output_path=exit_png,
        use_scintillator_extent=(sim_config_yaml_path is not None),
        sim_config_yaml_path=sim_config_yaml_path,
        xy_range_override=xy_range_override,
    )
    optical_interface_photons_to_image(hdf5_path, output_path=interface_png)
    if transport_hdf5_path is not None and transport_hdf5_path.exists():
        intensifier_photons_to_image(
            transport_hdf5_path,
            output_path=intensifier_png,
        )
    else:
        intensifier_png = None

    print(f"Input HDF5: {hdf5_path}")
    if xy_range_override is not None:
        print(f"Origin/exit XY limits: {xy_range_override}")
    elif sim_config_yaml_path is not None:
        print(f"SimConfig YAML (for origin/exit extent): {sim_config_yaml_path}")
    else:
        print("Origin/exit XY limits: inferred from HDF5 data bounds")
    print("Wrote images:")
    print(f"  - {neutron_png}")
    print(f"  - {origins_png}")
    print(f"  - {exit_png}")
    print(f"  - {interface_png}")
    if intensifier_png is not None:
        print(f"  - {intensifier_png}")
        print(f"Transport HDF5: {transport_hdf5_path}")
    else:
        print(
            "  - (skipped) photons_intensifier_hits.png "
            "[transport HDF5 not found]"
        )


if __name__ == "__main__":
    main()
