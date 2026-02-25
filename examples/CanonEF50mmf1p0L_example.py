"""YAML-driven CanonEF50mmf1p0L example macro generator.

This script reads all example settings from:
`examples/CanonEF50mmf1p0L_example.yaml`

YAML responsibilities:
- SimConfig fields (lens + geometry + output settings).
"""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure repository root is importable when this file is run directly.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.config.ConfigIO import (  # noqa: E402
    from_yaml,
    resolve_run_environment_paths,
    write_macro,
)

# Canon example YAML path lives next to this script.
EXAMPLE_YAML_PATH = Path(__file__).with_suffix(".yaml")


def main() -> None:
    """Generate a runnable Canon EF 50 mm f/1.0L macro from YAML settings."""

    config = from_yaml(EXAMPLE_YAML_PATH)

    write_macro(
        config,
        include_output=True,
        include_run_initialize=True,
        overwrite=True,
    )
    paths = resolve_run_environment_paths(config)
    macro_path = paths.macro_file
    effective_macro_path = macro_path

    print(f"Loaded YAML: {EXAMPLE_YAML_PATH.resolve()}")
    print(f"Wrote macro: {effective_macro_path}")
    print(f"Output stage directory: {paths.simulated_photons}")
    print(
        "Expected HDF5 target: "
        f"{paths.simulated_photons / 'photon_optical_interface_hits.h5'}"
    )
    print(f"Run with: pixi run g4emi {effective_macro_path}")


if __name__ == "__main__":
    main()
