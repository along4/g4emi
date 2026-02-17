"""YAML-driven CanonEF50mmf1p0L example macro generator.

This script reads all example settings from:
`examples/CanonEF50mmf1p0L_example.yaml`

YAML responsibilities:
- SimConfig fields (lens + geometry + output settings).
- Optional output macro destination path.
- Extra macro commands to append (GPS + beamOn block).
"""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure repository root is importable when this file is run directly.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.config.ConfigIO import (  # noqa: E402
    append_macro_commands,
    ensure_directory,
    ensure_output_directories,
    from_yaml,
    load_yaml_mapping,
    resolve_default_macro_path,
    resolve_optional_path,
    resolve_output_stage_directory,
    write_macro,
)

# Canon example YAML path lives next to this script.
EXAMPLE_YAML_PATH = Path(__file__).with_suffix(".yaml")


def main() -> None:
    """Generate a runnable Canon EF 50 mm f/1.0L macro from YAML settings."""

    payload = load_yaml_mapping(EXAMPLE_YAML_PATH)

    # SimConfig validates `output_path` existence, so create it before loading
    # via `from_yaml(...)` when the YAML supplies a path.
    output_path = payload.get("output_path")
    if isinstance(output_path, str) and output_path.strip():
        ensure_directory(output_path)

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
    append_commands = payload.get("append_macro_commands")
    if append_commands is not None:
        append_macro_commands(
            effective_macro_path,
            append_commands,
            key_name="append_macro_commands",
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
