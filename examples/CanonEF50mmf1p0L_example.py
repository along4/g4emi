"""YAML-driven CanonEF50mmf1p0L example macro generator.

This script reads all example settings from:
`examples/CanonEF50mmf1p0L_example.yaml`

YAML responsibilities:
- SimConfig fields (lens + geometry + output settings).
- Optional output macro destination path.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure repository root is importable when this file is run directly.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.config.ConfigIO import (  # noqa: E402
    ensure_output_directories,
    from_yaml,
    load_yaml_mapping,
    resolve_default_macro_path,
    resolve_output_stage_directory,
    write_macro,
)
from src.config.utilsConfig import resolve_optional_path  # noqa: E402

# Canon example YAML path lives next to this script.
EXAMPLE_YAML_PATH = Path(__file__).with_suffix(".yaml")


def main() -> None:
    """Generate a runnable Canon EF 50 mm f/1.0L macro from YAML settings."""

    payload = load_yaml_mapping(EXAMPLE_YAML_PATH)

    config = from_yaml(EXAMPLE_YAML_PATH)
    output_stage_dir = ensure_output_directories(config)
    macro_path = resolve_optional_path(
        payload.get("macro_output_path"),
        key_name="macro_output_path",
        base_directory=Path(__file__).resolve().parents[1],
    )
    if macro_path is not None:
        macro_path.parent.mkdir(parents=True, exist_ok=True)

    write_macro(
        config,
        macro_path=macro_path,
        include_output=True,
        include_run_initialize=True,
        create_output_directories=False,
        overwrite=True,
    )
    effective_macro_path = (
        macro_path if macro_path is not None else resolve_default_macro_path(config)
    )

    print(f"Loaded YAML: {EXAMPLE_YAML_PATH.resolve()}")
    print(f"Wrote macro: {effective_macro_path}")
    print(f"Output stage directory: {output_stage_dir}")
    print(
        "Expected HDF5 target: "
        f"{resolve_output_stage_directory(config) / 'photon_optical_interface_hits.h5'}"
    )
    print(f"Run with: pixi run g4emi {effective_macro_path}")


if __name__ == "__main__":
    main()
