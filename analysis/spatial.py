"""Spatial quick-look plotting helpers for simulation and transport outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
from analysis.io import (
    decode_species,
    intensifier_input_screen_from_attrs,
    read_structured_dataset,
    read_structured_dataset_with_file_attrs,
    require_fields,
)
from analysis.plotting import plot_histogram_2d, save_and_maybe_show
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from src.common.hdf5_schema import PHOTON_SCINT_EXIT_X_FIELD, PHOTON_SCINT_EXIT_Y_FIELD

XYRange = tuple[tuple[float, float], tuple[float, float]]


def _histogram_image(
    x_mm: np.ndarray,
    y_mm: np.ndarray,
    bins: int | Sequence[int],
    xy_range: XYRange | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build a 2D histogram image and the corresponding bin edges."""

    if x_mm.size == 0 or y_mm.size == 0:
        if xy_range is None:
            raise ValueError("No points available to plot.")
        return np.histogram2d(
            np.array([], dtype=float),
            np.array([], dtype=float),
            bins=bins,
            range=xy_range,
        )

    return np.histogram2d(x_mm, y_mm, bins=bins, range=xy_range)


def _shared_xy_range(
    hdf5_path: str | Path,
    neutron_labels: Sequence[str],
) -> XYRange:
    """Compute a shared XY histogram range for neutron/origin/exit plots."""

    primaries = read_structured_dataset(hdf5_path, "primaries")
    photons = read_structured_dataset(hdf5_path, "photons")

    neutron_set = {label.lower() for label in neutron_labels}
    primary_labels = decode_species(primaries["primary_species"])
    neutron_mask = np.isin(primary_labels, list(neutron_set))

    x_values = [np.asarray(primaries["primary_x_mm"][neutron_mask], dtype=float)]
    y_values = [np.asarray(primaries["primary_y_mm"][neutron_mask], dtype=float)]
    x_values.append(np.asarray(photons["photon_origin_x_mm"], dtype=float))
    y_values.append(np.asarray(photons["photon_origin_y_mm"], dtype=float))

    exit_x = np.asarray(photons[PHOTON_SCINT_EXIT_X_FIELD], dtype=float)
    exit_y = np.asarray(photons[PHOTON_SCINT_EXIT_Y_FIELD], dtype=float)
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

    return (
        (float(np.min(x_all)), float(np.max(x_all))),
        (float(np.min(y_all)), float(np.max(y_all))),
    )


def _scintillator_xy_range_from_sim_config(sim_config_yaml_path: str | Path) -> XYRange:
    """Read scintillator XY extent from SimConfig YAML."""

    path = Path(sim_config_yaml_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"SimConfig YAML not found: {path}")

    try:
        from src.config.ConfigIO import from_yaml
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Could not import `src.config.ConfigIO.from_yaml` required for "
            "scintillator-based plot extents. Run in the project environment "
            "(for example: `pixi run ...`)."
        ) from exc

    config = from_yaml(path)
    center_x = float(config.scintillator.position_mm.x_mm)
    center_y = float(config.scintillator.position_mm.y_mm)
    size_x = float(config.scintillator.dimension_mm.x_mm)
    size_y = float(config.scintillator.dimension_mm.y_mm)
    return (
        (center_x - 0.5 * size_x, center_x + 0.5 * size_x),
        (center_y - 0.5 * size_y, center_y + 0.5 * size_y),
    )


def _resolve_scintillator_plot_xy_range(
    *,
    hdf5_path: str | Path,
    neutron_labels: Sequence[str],
    shared_range: bool,
    use_scintillator_extent: bool,
    sim_config_yaml_path: str | Path | None,
    xy_range_override: XYRange | None,
) -> XYRange | None:
    """Resolve XY range with precedence: override -> scintillator -> shared."""

    if xy_range_override is not None:
        return xy_range_override
    if use_scintillator_extent and sim_config_yaml_path is not None:
        return _scintillator_xy_range_from_sim_config(sim_config_yaml_path)
    if shared_range:
        return _shared_xy_range(hdf5_path, neutron_labels)
    return None


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

    primaries = read_structured_dataset(hdf5_path, "primaries")
    required = {"primary_species", "primary_x_mm", "primary_y_mm"}
    require_fields(primaries, required, dataset_name="primaries")

    labels = decode_species(primaries["primary_species"])
    neutron_set = {label.lower() for label in neutron_labels}
    mask = np.isin(labels, list(neutron_set))

    x_mm = np.asarray(primaries["primary_x_mm"][mask], dtype=float)
    y_mm = np.asarray(primaries["primary_y_mm"][mask], dtype=float)
    xy_range = _shared_xy_range(hdf5_path, neutron_labels) if shared_range else None
    hist, x_edges, y_edges = _histogram_image(x_mm, y_mm, bins, xy_range=xy_range)

    return plot_histogram_2d(
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
    use_scintillator_extent: bool = True,
    sim_config_yaml_path: str | Path | None = None,
    xy_range_override: XYRange | None = None,
) -> tuple[Figure, Axes]:
    """Plot photon origin coordinates (`/photons`) as a 2D image."""

    photons = read_structured_dataset(hdf5_path, "photons")
    required = {"photon_origin_x_mm", "photon_origin_y_mm"}
    require_fields(photons, required, dataset_name="photons")

    x_mm = np.asarray(photons["photon_origin_x_mm"], dtype=float)
    y_mm = np.asarray(photons["photon_origin_y_mm"], dtype=float)
    xy_range = _resolve_scintillator_plot_xy_range(
        hdf5_path=hdf5_path,
        neutron_labels=neutron_labels,
        shared_range=shared_range,
        use_scintillator_extent=use_scintillator_extent,
        sim_config_yaml_path=sim_config_yaml_path,
        xy_range_override=xy_range_override,
    )
    hist, x_edges, y_edges = _histogram_image(x_mm, y_mm, bins, xy_range=xy_range)

    return plot_histogram_2d(
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
    use_scintillator_extent: bool = True,
    sim_config_yaml_path: str | Path | None = None,
    xy_range_override: XYRange | None = None,
) -> tuple[Figure, Axes]:
    """Plot photon scintillator-exit coordinates (`/photons`) as a 2D image."""

    photons = read_structured_dataset(hdf5_path, "photons")
    required = {PHOTON_SCINT_EXIT_X_FIELD, PHOTON_SCINT_EXIT_Y_FIELD}
    require_fields(photons, required, dataset_name="photons")

    x_mm = np.asarray(photons[PHOTON_SCINT_EXIT_X_FIELD], dtype=float)
    y_mm = np.asarray(photons[PHOTON_SCINT_EXIT_Y_FIELD], dtype=float)
    finite_exit_mask = np.isfinite(x_mm) & np.isfinite(y_mm)
    x_mm = x_mm[finite_exit_mask]
    y_mm = y_mm[finite_exit_mask]
    xy_range = _resolve_scintillator_plot_xy_range(
        hdf5_path=hdf5_path,
        neutron_labels=neutron_labels,
        shared_range=shared_range,
        use_scintillator_extent=use_scintillator_extent,
        sim_config_yaml_path=sim_config_yaml_path,
        xy_range_override=xy_range_override,
    )
    hist, x_edges, y_edges = _histogram_image(x_mm, y_mm, bins, xy_range=xy_range)

    return plot_histogram_2d(
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

    photons = read_structured_dataset(hdf5_path, "photons")
    required = {"optical_interface_hit_x_mm", "optical_interface_hit_y_mm"}
    require_fields(photons, required, dataset_name="photons")

    mask = np.ones(len(photons), dtype=bool)
    if (
        require_positive_energy
        and "optical_interface_hit_energy_eV" in (photons.dtype.names or ())
    ):
        mask &= np.asarray(photons["optical_interface_hit_energy_eV"], dtype=float) > 0.0

    x_mm = np.asarray(photons["optical_interface_hit_x_mm"][mask], dtype=float)
    y_mm = np.asarray(photons["optical_interface_hit_y_mm"][mask], dtype=float)
    hist, x_edges, y_edges = _histogram_image(x_mm, y_mm, bins)

    return plot_histogram_2d(
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
    overlay_input_screen: bool = True,
    cmap: str = "viridis",
    log_scale: bool = True,
    output_path: str | Path | None = None,
    show: bool = False,
) -> tuple[Figure, Axes]:
    """Plot transported intensifier-plane photon hits (`/transported_photons`)."""

    transported, file_attrs = read_structured_dataset_with_file_attrs(
        hdf5_path,
        "transported_photons",
    )
    required = {"intensifier_hit_x_mm", "intensifier_hit_y_mm"}
    require_fields(transported, required, dataset_name="transported_photons")
    transported_names = set(transported.dtype.names or ())

    screen = intensifier_input_screen_from_attrs(file_attrs)
    xy_range = None
    if screen is not None:
        center_x_mm, center_y_mm, diameter_mm = screen
        radius_mm = 0.5 * diameter_mm
        xy_range = (
            (center_x_mm - radius_mm, center_x_mm + radius_mm),
            (center_y_mm - radius_mm, center_y_mm + radius_mm),
        )

    mask = np.ones(len(transported), dtype=bool)
    reached_mask = np.ones(len(transported), dtype=bool)
    if "reached_intensifier" in transported_names:
        reached_mask = np.asarray(transported["reached_intensifier"], dtype=bool)
    else:
        reached_mask = (
            np.isfinite(np.asarray(transported["intensifier_hit_x_mm"], dtype=float))
            & np.isfinite(np.asarray(transported["intensifier_hit_y_mm"], dtype=float))
        )
    if require_reached_intensifier:
        mask &= reached_mask

    out_of_bounds_fraction = None
    if "in_bounds" in transported_names:
        in_bounds_mask = np.asarray(transported["in_bounds"], dtype=bool)
        reached_count = int(np.count_nonzero(reached_mask))
        if reached_count > 0:
            out_of_bounds_count = int(np.count_nonzero(reached_mask & ~in_bounds_mask))
            out_of_bounds_fraction = float(out_of_bounds_count / reached_count)

    x_mm = np.asarray(transported["intensifier_hit_x_mm"][mask], dtype=float)
    y_mm = np.asarray(transported["intensifier_hit_y_mm"][mask], dtype=float)
    finite_mask = np.isfinite(x_mm) & np.isfinite(y_mm)
    x_mm = x_mm[finite_mask]
    y_mm = y_mm[finite_mask]
    hist, x_edges, y_edges = _histogram_image(x_mm, y_mm, bins, xy_range=xy_range)

    title = "Intensifier Photon Hits"
    if out_of_bounds_fraction is not None:
        title = f"{title} (out-of-bounds: {out_of_bounds_fraction:.1%})"

    fig, ax = plot_histogram_2d(
        hist,
        x_edges,
        y_edges,
        title=title,
        cmap=cmap,
        log_scale=log_scale,
        output_path=None,
        show=False,
    )

    if screen is not None and overlay_input_screen:
        center_x_mm, center_y_mm, diameter_mm = screen
        radius_mm = 0.5 * diameter_mm
        ax.add_patch(
            plt.Circle(
                (center_x_mm, center_y_mm),
                radius_mm,
                fill=False,
                color="white",
                linewidth=1.25,
                linestyle="--",
            )
        )
        ax.set_xlim(center_x_mm - radius_mm, center_x_mm + radius_mm)
        ax.set_ylim(center_y_mm - radius_mm, center_y_mm + radius_mm)

    save_and_maybe_show(fig, output_path=output_path, show=show)
    return fig, ax


__all__ = [
    "intensifier_photons_to_image",
    "neutron_hits_to_image",
    "optical_interface_photons_to_image",
    "photon_exit_to_image",
    "photon_origins_to_image",
]
