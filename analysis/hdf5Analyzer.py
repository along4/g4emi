"""Lightweight HDF5 plotting utilities for g4emi outputs.

This module converts key HDF5 datasets into 2D histogram images for quick
analysis.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

try:
    import h5py
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "h5py is required for HDF5 analysis. Install project dependencies with "
        "`pixi install` (after pulling latest changes)."
    ) from exc
import numpy as np
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.colors import LogNorm
from matplotlib.figure import Figure


def _read_structured_dataset(hdf5_path: str | Path, dataset_name: str) -> np.ndarray:
    """Read one structured dataset from an HDF5 file."""

    path = Path(hdf5_path)
    if not path.exists():
        raise FileNotFoundError(f"HDF5 file not found: {path}")

    with h5py.File(path, "r") as handle:
        if dataset_name not in handle:
            raise KeyError(f"Dataset {dataset_name!r} not found in {path}")
        return handle[dataset_name][:]


def _decode_species(values: np.ndarray) -> np.ndarray:
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


def _histogram_image(
    x_mm: np.ndarray,
    y_mm: np.ndarray,
    bins: int | Sequence[int],
    xy_range: tuple[tuple[float, float], tuple[float, float]] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build a 2D histogram image and the corresponding bin edges."""

    if x_mm.size == 0 or y_mm.size == 0:
        raise ValueError("No points available to plot.")

    return np.histogram2d(x_mm, y_mm, bins=bins, range=xy_range)


def _photon_exit_field_names(photons: np.ndarray) -> tuple[str, str]:
    """Resolve scintillator-exit field names across schema versions."""

    names = set(photons.dtype.names or ())
    if {"photon_scint_exit_x_mm", "photon_scint_exit_y_mm"}.issubset(names):
        return "photon_scint_exit_x_mm", "photon_scint_exit_y_mm"
    if {"scint_exit_x_mm", "scint_exit_y_mm"}.issubset(names):
        return "scint_exit_x_mm", "scint_exit_y_mm"
    raise KeyError(
        "/photons is missing scintillator-exit fields. Expected either "
        "('photon_scint_exit_x_mm', 'photon_scint_exit_y_mm') or "
        "('scint_exit_x_mm', 'scint_exit_y_mm')."
    )


def _shared_xy_range(
    hdf5_path: str | Path,
    neutron_labels: Sequence[str],
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Compute a shared XY histogram range for neutron/origin/exit plots."""

    primaries = _read_structured_dataset(hdf5_path, "primaries")
    photons = _read_structured_dataset(hdf5_path, "photons")

    neutron_set = {label.lower() for label in neutron_labels}
    primary_labels = _decode_species(primaries["primary_species"])
    neutron_mask = np.isin(primary_labels, list(neutron_set))

    x_values = [np.asarray(primaries["primary_x_mm"][neutron_mask], dtype=float)]
    y_values = [np.asarray(primaries["primary_y_mm"][neutron_mask], dtype=float)]
    x_values.append(np.asarray(photons["photon_origin_x_mm"], dtype=float))
    y_values.append(np.asarray(photons["photon_origin_y_mm"], dtype=float))

    exit_x_field, exit_y_field = _photon_exit_field_names(photons)
    exit_x = np.asarray(photons[exit_x_field], dtype=float)
    exit_y = np.asarray(photons[exit_y_field], dtype=float)
    # Missing scintillator exits are encoded as NaN; exclude them from range
    # calculation so finite origin/hit coordinates still define valid bounds.
    finite_exit_mask = np.isfinite(exit_x) & np.isfinite(exit_y)
    x_values.append(exit_x[finite_exit_mask])
    y_values.append(exit_y[finite_exit_mask])

    x_all = np.concatenate([values for values in x_values if values.size > 0])
    y_all = np.concatenate([values for values in y_values if values.size > 0])
    x_all = x_all[np.isfinite(x_all)]
    y_all = y_all[np.isfinite(y_all)]
    if x_all.size == 0 or y_all.size == 0:
        raise ValueError(
            "Unable to compute shared range because no finite XY points were found."
        )

    return ((float(np.min(x_all)), float(np.max(x_all))), (float(np.min(y_all)), float(np.max(y_all))))


def _plot_histogram(
    hist: np.ndarray,
    x_edges: np.ndarray,
    y_edges: np.ndarray,
    *,
    title: str,
    cmap: str,
    log_scale: bool,
    output_path: str | Path | None,
    show: bool,
) -> tuple[Figure, Axes]:
    """Render histogram image to a matplotlib figure."""

    fig, ax = plt.subplots(figsize=(7, 6))

    norm = None
    if log_scale and np.any(hist > 0):
        norm = LogNorm(vmin=1.0, vmax=float(hist.max()))

    image = ax.imshow(
        hist.T,
        origin="lower",
        extent=[x_edges[0], x_edges[-1], y_edges[0], y_edges[-1]],
        interpolation="nearest",
        aspect="equal",
        cmap=cmap,
        norm=norm,
    )

    ax.set_title(title)
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    fig.colorbar(image, ax=ax, label="counts")
    fig.tight_layout()

    if output_path is not None:
        fig.savefig(Path(output_path), dpi=150)

    if show:
        plt.show()

    return fig, ax


def neutron_hits_to_image(
    hdf5_path: str | Path,
    bins: int | Sequence[int] = (256, 256),
    *,
    neutron_labels: Sequence[str] = ("n", "neutron"),
    cmap: str = "viridis",
    log_scale: bool = True,
    output_path: str | Path | None = None,
    show: bool = False,
    shared_range: bool = True,
) -> tuple[Figure, Axes]:
    """Plot primary neutron hit positions (`/primaries`) as a 2D image."""

    primaries = _read_structured_dataset(hdf5_path, "primaries")
    required = {"primary_species", "primary_x_mm", "primary_y_mm"}
    if not required.issubset(set(primaries.dtype.names or ())):
        raise KeyError(f"/primaries is missing required fields: {sorted(required)}")

    labels = _decode_species(primaries["primary_species"])
    neutron_set = {label.lower() for label in neutron_labels}
    mask = np.isin(labels, list(neutron_set))

    x_mm = np.asarray(primaries["primary_x_mm"][mask], dtype=float)
    y_mm = np.asarray(primaries["primary_y_mm"][mask], dtype=float)
    xy_range = _shared_xy_range(hdf5_path, neutron_labels) if shared_range else None
    hist, x_edges, y_edges = _histogram_image(x_mm, y_mm, bins, xy_range=xy_range)

    return _plot_histogram(
        hist,
        x_edges,
        y_edges,
        title="Neutron Hits (Primaries)",
        cmap=cmap,
        log_scale=log_scale,
        output_path=output_path,
        show=show,
    )


def photon_origins_to_image(
    hdf5_path: str | Path,
    bins: int | Sequence[int] = (256, 256),
    *,
    cmap: str = "viridis",
    log_scale: bool = True,
    output_path: str | Path | None = None,
    show: bool = False,
    shared_range: bool = True,
    neutron_labels: Sequence[str] = ("n", "neutron"),
) -> tuple[Figure, Axes]:
    """Plot photon origin coordinates (`/photons`) as a 2D image."""

    photons = _read_structured_dataset(hdf5_path, "photons")
    required = {"photon_origin_x_mm", "photon_origin_y_mm"}
    if not required.issubset(set(photons.dtype.names or ())):
        raise KeyError(f"/photons is missing required fields: {sorted(required)}")

    x_mm = np.asarray(photons["photon_origin_x_mm"], dtype=float)
    y_mm = np.asarray(photons["photon_origin_y_mm"], dtype=float)
    xy_range = _shared_xy_range(hdf5_path, neutron_labels) if shared_range else None
    hist, x_edges, y_edges = _histogram_image(x_mm, y_mm, bins, xy_range=xy_range)

    return _plot_histogram(
        hist,
        x_edges,
        y_edges,
        title="Photon Origins",
        cmap=cmap,
        log_scale=log_scale,
        output_path=output_path,
        show=show,
    )


def photon_exit_to_image(
    hdf5_path: str | Path,
    bins: int | Sequence[int] = (256, 256),
    *,
    cmap: str = "viridis",
    log_scale: bool = True,
    output_path: str | Path | None = None,
    show: bool = False,
    shared_range: bool = True,
    neutron_labels: Sequence[str] = ("n", "neutron"),
) -> tuple[Figure, Axes]:
    """Plot photon scintillator-exit coordinates (`/photons`) as a 2D image."""

    photons = _read_structured_dataset(hdf5_path, "photons")
    x_field, y_field = _photon_exit_field_names(photons)

    x_mm = np.asarray(photons[x_field], dtype=float)
    y_mm = np.asarray(photons[y_field], dtype=float)
    finite_exit_mask = np.isfinite(x_mm) & np.isfinite(y_mm)
    x_mm = x_mm[finite_exit_mask]
    y_mm = y_mm[finite_exit_mask]
    xy_range = _shared_xy_range(hdf5_path, neutron_labels) if shared_range else None
    hist, x_edges, y_edges = _histogram_image(x_mm, y_mm, bins, xy_range=xy_range)

    return _plot_histogram(
        hist,
        x_edges,
        y_edges,
        title="Photon Exit Points",
        cmap=cmap,
        log_scale=log_scale,
        output_path=output_path,
        show=show,
    )


def optical_interface_photons_to_image(
    hdf5_path: str | Path,
    bins: int | Sequence[int] = (256, 256),
    *,
    require_positive_energy: bool = True,
    cmap: str = "viridis",
    log_scale: bool = True,
    output_path: str | Path | None = None,
    show: bool = False,
) -> tuple[Figure, Axes]:
    """Plot optical-interface photon hits (`/photons`) as a 2D image."""

    photons = _read_structured_dataset(hdf5_path, "photons")
    required = {"optical_interface_hit_x_mm", "optical_interface_hit_y_mm"}
    if not required.issubset(set(photons.dtype.names or ())):
        raise KeyError(f"/photons is missing required fields: {sorted(required)}")

    mask = np.ones(len(photons), dtype=bool)
    if (
        require_positive_energy
        and "optical_interface_hit_energy_eV" in (photons.dtype.names or ())
    ):
        mask &= np.asarray(photons["optical_interface_hit_energy_eV"], dtype=float) > 0.0

    x_mm = np.asarray(photons["optical_interface_hit_x_mm"][mask], dtype=float)
    y_mm = np.asarray(photons["optical_interface_hit_y_mm"][mask], dtype=float)
    hist, x_edges, y_edges = _histogram_image(x_mm, y_mm, bins)

    return _plot_histogram(
        hist,
        x_edges,
        y_edges,
        title="Optical Interface Photon Hits",
        cmap=cmap,
        log_scale=log_scale,
        output_path=output_path,
        show=show,
    )


def intensifier_photons_to_image(
    hdf5_path: str | Path,
    bins: int | Sequence[int] = (256, 256),
    *,
    require_reached_intensifier: bool = True,
    cmap: str = "viridis",
    log_scale: bool = True,
    output_path: str | Path | None = None,
    show: bool = False,
) -> tuple[Figure, Axes]:
    """Plot transported intensifier-plane photon hits (`/transported_photons`)."""

    transported = _read_structured_dataset(hdf5_path, "transported_photons")
    required = {"intensifier_hit_x_mm", "intensifier_hit_y_mm"}
    if not required.issubset(set(transported.dtype.names or ())):
        raise KeyError(
            "/transported_photons is missing required fields: "
            f"{sorted(required)}"
        )

    mask = np.ones(len(transported), dtype=bool)
    if (
        require_reached_intensifier
        and "reached_intensifier" in (transported.dtype.names or ())
    ):
        mask &= np.asarray(transported["reached_intensifier"], dtype=bool)

    x_mm = np.asarray(transported["intensifier_hit_x_mm"][mask], dtype=float)
    y_mm = np.asarray(transported["intensifier_hit_y_mm"][mask], dtype=float)
    finite_mask = np.isfinite(x_mm) & np.isfinite(y_mm)
    x_mm = x_mm[finite_mask]
    y_mm = y_mm[finite_mask]
    hist, x_edges, y_edges = _histogram_image(x_mm, y_mm, bins)

    return _plot_histogram(
        hist,
        x_edges,
        y_edges,
        title="Intensifier Photon Hits",
        cmap=cmap,
        log_scale=log_scale,
        output_path=output_path,
        show=show,
    )


__all__ = [
    "neutron_hits_to_image",
    "photon_origins_to_image",
    "photon_exit_to_image",
    "optical_interface_photons_to_image",
    "intensifier_photons_to_image",
]
