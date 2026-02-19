"""Shared path utilities for configuration modules.

These helpers are intentionally dependency-light so both `SimConfig` and
`ConfigIO` can use consistent path behavior without introducing circular
imports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def repo_root() -> Path:
    """Return repository root inferred from this module location."""

    return Path(__file__).resolve().parents[2]


def resolve_path(path: str | Path, *, base_directory: str | Path | None = None) -> Path:
    """Resolve a path to an absolute path.

    Behavior:
    - Expands `~`.
    - Absolute inputs are returned as-is (resolved).
    - Relative inputs are resolved against `base_directory` when provided,
      otherwise against repository root.
    """

    resolved = Path(path).expanduser()
    if resolved.is_absolute():
        return resolved.resolve()

    if base_directory is None:
        base = repo_root()
    else:
        base = Path(base_directory).expanduser()
        if not base.is_absolute():
            base = repo_root() / base
        base = base.resolve()

    return (base / resolved).resolve()


def resolve_optional_path(
    value: Any,
    *,
    key_name: str,
    base_directory: str | Path | None = None,
) -> Path | None:
    """Resolve an optional YAML path-like value into an absolute path.

    Validation behavior:
    - `None` or blank string -> `None`
    - non-string non-null -> `ValueError`
    - relative string -> resolved against `base_directory` (or repo root)
    """

    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"YAML key `{key_name}` must be a string when provided.")
    if not value.strip():
        return None
    return resolve_path(value, base_directory=base_directory)
