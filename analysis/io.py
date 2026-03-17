"""Shared HDF5 file and dataset access helpers for analysis code."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

try:
    import h5py
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "h5py is required for HDF5 analysis. Install project dependencies with "
        "`pixi install` (after pulling latest changes)."
    ) from exc
import numpy as np


def read_structured_dataset(hdf5_path: str | Path, dataset_name: str) -> np.ndarray:
    """Read one structured dataset from an HDF5 file."""

    path = Path(hdf5_path)
    if not path.exists():
        raise FileNotFoundError(f"HDF5 file not found: {path}")

    with h5py.File(path, "r") as handle:
        if dataset_name not in handle:
            raise KeyError(f"Dataset {dataset_name!r} not found in {path}")
        return handle[dataset_name][:]


def read_structured_dataset_with_file_attrs(
    hdf5_path: str | Path,
    dataset_name: str,
) -> tuple[np.ndarray, dict[str, object]]:
    """Read one structured dataset plus root-level HDF5 file attributes."""

    path = Path(hdf5_path)
    if not path.exists():
        raise FileNotFoundError(f"HDF5 file not found: {path}")

    with h5py.File(path, "r") as handle:
        if dataset_name not in handle:
            raise KeyError(f"Dataset {dataset_name!r} not found in {path}")
        attrs = {str(key): handle.attrs[key] for key in handle.attrs.keys()}
        return handle[dataset_name][:], attrs


def decode_species(values: np.ndarray) -> np.ndarray:
    """Decode fixed-length HDF5 string arrays into lowercase Python strings."""

    return np.array(
        [
            (value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else str(value))
            .strip("\x00")
            .strip()
            .lower()
            for value in values
        ],
        dtype=object,
    )


def require_fields(
    dataset: np.ndarray,
    required_fields: Iterable[str],
    *,
    dataset_name: str,
) -> None:
    """Raise a helpful error when a structured dataset is missing fields."""

    required = set(required_fields)
    available = set(dataset.dtype.names or ())
    if required.issubset(available):
        return
    raise KeyError(f"/{dataset_name} is missing required fields: {sorted(required)}")


def intensifier_input_screen_from_attrs(
    attrs: dict[str, object],
) -> tuple[float, float, float] | None:
    """Return `(center_x_mm, center_y_mm, diameter_mm)` from file attrs."""

    if "intensifier_input_screen_diameter_mm" not in attrs:
        return None
    if not bool(attrs.get("intensifier_input_screen_defined", True)):
        return None

    diameter_mm = float(attrs["intensifier_input_screen_diameter_mm"])
    center_raw = attrs.get("intensifier_input_screen_center_mm")
    if center_raw is None:
        return None
    center = np.asarray(center_raw, dtype=float).reshape(-1)
    if center.size != 2:
        return None
    center_x_mm = float(center[0])
    center_y_mm = float(center[1])

    if not np.isfinite(diameter_mm) or diameter_mm <= 0.0:
        return None
    if not np.isfinite(center_x_mm) or not np.isfinite(center_y_mm):
        return None
    return (center_x_mm, center_y_mm, diameter_mm)


__all__ = [
    "decode_species",
    "intensifier_input_screen_from_attrs",
    "read_structured_dataset",
    "read_structured_dataset_with_file_attrs",
    "require_fields",
]
