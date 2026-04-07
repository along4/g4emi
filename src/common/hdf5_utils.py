"""Shared HDF5 utility helpers used across pipeline stages."""

from __future__ import annotations

try:
    import h5py
except ModuleNotFoundError as exc:  # pragma: no cover - dependency availability varies
    raise ModuleNotFoundError(
        "h5py is required for HDF5 utilities. "
        "Install project dependencies (for example: pixi install)."
    ) from exc


def copy_dataset_if_present(
    source: h5py.File,
    destination: h5py.File,
    dataset_name: str,
) -> None:
    """Copy one dataset when present in the source HDF5 file."""

    if dataset_name in source:
        source.copy(dataset_name, destination)
