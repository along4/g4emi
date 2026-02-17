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
from typing import Any

import yaml

# Ensure repository root is importable when this file is run directly.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.config.ConfigIO import (  # noqa: E402
    ensure_directory,
    ensure_output_directories,
    from_yaml,
    resolve_default_macro_path,
    resolve_output_stage_directory,
    write_macro,
)

# Canon example YAML path lives next to this script.
EXAMPLE_YAML_PATH = Path(__file__).with_suffix(".yaml")


def _load_yaml_payload(yaml_path: Path) -> dict[str, Any]:
    """Load raw YAML payload for script-level settings.

    This parser is intentionally strict about top-level mapping shape, while
    leaving individual optional keys (for example `macro_output_path`) to be
    interpreted by dedicated helper functions.
    """

    if not yaml_path.exists():
        raise FileNotFoundError(f"Example YAML file not found: {yaml_path}")

    parsed = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        raise ValueError(f"Example YAML must be a top-level mapping: {yaml_path}")

    return parsed


def _resolve_macro_output_path(payload: dict[str, Any]) -> Path | None:
    """Resolve optional macro output path from YAML.

    Behavior:
    - If `macro_output_path` is missing or blank, return `None` so ConfigIO
      default path policy is used.
    - If provided, resolve relative paths against repository root and return
      an absolute path.
    - Reject non-string non-null values to catch malformed YAML early.
    """

    raw_macro_path = payload.get("macro_output_path")
    if raw_macro_path is None:
        return None
    if not isinstance(raw_macro_path, str):
        raise ValueError("YAML key `macro_output_path` must be a string when provided.")
    if not raw_macro_path.strip():
        return None

    macro_path = Path(raw_macro_path).expanduser()
    if not macro_path.is_absolute():
        macro_path = Path(__file__).resolve().parents[1] / macro_path
    return macro_path.resolve()


def _append_macro_commands(macro_path: Path, payload: dict[str, Any]) -> None:
    """Append YAML-provided command lines to generated macro file."""

    commands = payload.get("append_macro_commands")
    if commands is None:
        return
    if not isinstance(commands, list) or not all(
        isinstance(item, str) for item in commands
    ):
        raise ValueError("YAML key `append_macro_commands` must be a list of strings.")

    body = macro_path.read_text(encoding="utf-8")
    macro_path.write_text(body + "\n" + "\n".join(commands) + "\n", encoding="utf-8")


def main() -> None:
    """Generate a runnable Canon EF 50 mm f/1.0L macro from YAML settings."""

    payload = _load_yaml_payload(EXAMPLE_YAML_PATH)

    # SimConfig validates `output_path` existence, so create it before loading
    # via `from_yaml(...)` when the YAML supplies a path.
    output_path = payload.get("output_path")
    if isinstance(output_path, str) and output_path.strip():
        ensure_directory(output_path)

    config = from_yaml(EXAMPLE_YAML_PATH)
    output_stage_dir = ensure_output_directories(config)
    macro_path = _resolve_macro_output_path(payload)
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
    _append_macro_commands(effective_macro_path, payload)

    print(f"Loaded YAML: {EXAMPLE_YAML_PATH.resolve()}")
    print(f"Wrote macro: {effective_macro_path}")
    print(f"Output stage directory: {output_stage_dir}")
    print(
        "Expected HDF5 target: "
        f"{resolve_output_stage_directory(config) / 'photon_optical_interface_hits.h5'}"
    )
    print(f"Run with: ./build/g4emi {effective_macro_path}")


if __name__ == "__main__":
    main()
