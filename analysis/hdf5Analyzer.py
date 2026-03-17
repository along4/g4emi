"""Lightweight HDF5 plotting utilities for g4emi outputs.

This module converts key HDF5 datasets into 2D histogram images for quick
analysis.
"""

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
from analysis.plotting import (
    overlay_histogram_colors,
    plot_histogram_2d,
    save_and_maybe_show,
)
from analysis.timing import (
    PhotonCreationDelayFitResult,
    ScintillationDecayComponent,
    decay_model_bin_counts,
    fit_photon_creation_delay_histogram,
    photon_creation_delay_to_histogram,
    photon_creation_delays_ns,
)
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from src.common.hdf5_schema import (
    PHOTON_SCINT_EXIT_X_FIELD,
    PHOTON_SCINT_EXIT_Y_FIELD,
    SECONDARY_END_X_FIELD,
    SECONDARY_END_Y_FIELD,
    SECONDARY_END_Z_FIELD,
)

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


def _histogram_counts(
    values: np.ndarray,
    bins: int | Sequence[float],
) -> tuple[np.ndarray, np.ndarray]:
    """Build a 1D histogram and corresponding bin edges."""

    if values.size == 0:
        raise ValueError("No values available to plot.")
    return np.histogram(values, bins=bins)


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


def _projection_axes(plane: str) -> tuple[str, str]:
    """Return the in-plane axis labels for a requested 2D projection."""

    normalized = plane.strip().lower()
    if normalized not in {"xy", "xz", "yz"}:
        raise ValueError("plane must be one of: 'xy', 'xz', 'yz'.")
    return normalized[0], normalized[1]


def secondary_track_lengths_by_species_mm(
    hdf5_path: str | Path,
    *,
    secondary_species: Sequence[str] | None = None,
) -> dict[str, np.ndarray]:
    """Return secondary origin-to-end lengths grouped by species."""

    secondaries = read_structured_dataset(hdf5_path, "secondaries")
    required = {
        "secondary_species",
        "secondary_origin_x_mm",
        "secondary_origin_y_mm",
        "secondary_origin_z_mm",
        SECONDARY_END_X_FIELD,
        SECONDARY_END_Y_FIELD,
        SECONDARY_END_Z_FIELD,
    }
    require_fields(secondaries, required, dataset_name="secondaries")

    labels = decode_species(secondaries["secondary_species"])
    delta_x_mm = np.asarray(secondaries[SECONDARY_END_X_FIELD], dtype=float) - np.asarray(
        secondaries["secondary_origin_x_mm"],
        dtype=float,
    )
    delta_y_mm = np.asarray(secondaries[SECONDARY_END_Y_FIELD], dtype=float) - np.asarray(
        secondaries["secondary_origin_y_mm"],
        dtype=float,
    )
    delta_z_mm = np.asarray(secondaries[SECONDARY_END_Z_FIELD], dtype=float) - np.asarray(
        secondaries["secondary_origin_z_mm"],
        dtype=float,
    )
    track_lengths_mm = np.sqrt(
        np.square(delta_x_mm) + np.square(delta_y_mm) + np.square(delta_z_mm)
    )
    finite_mask = np.isfinite(track_lengths_mm) & (track_lengths_mm >= 0.0)
    labels = labels[finite_mask]
    track_lengths_mm = track_lengths_mm[finite_mask]

    if secondary_species is not None:
        selected = {label.lower() for label in secondary_species}
        selection_mask = np.isin(labels, list(selected))
        labels = labels[selection_mask]
        track_lengths_mm = track_lengths_mm[selection_mask]

    if track_lengths_mm.size == 0:
        raise ValueError(
            "No finite non-negative secondary track lengths were found in the HDF5 data."
        )

    grouped: dict[str, np.ndarray] = {}
    for species in sorted(set(labels.tolist())):
        species_mask = labels == species
        grouped[species] = np.asarray(track_lengths_mm[species_mask], dtype=float)
    return grouped




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
    """Plot photon origin coordinates (`/photons`) as a 2D image.

    XY-range precedence:
    1. `xy_range_override` (explicit user range)
    2. SimConfig scintillator extent (`sim_config_yaml_path`) when enabled
    3. legacy shared-data range (`shared_range=True`)
    """

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
    """Plot photon scintillator-exit coordinates (`/photons`) as a 2D image.

    XY-range precedence:
    1. `xy_range_override` (explicit user range)
    2. SimConfig scintillator extent (`sim_config_yaml_path`) when enabled
    3. legacy shared-data range (`shared_range=True`)
    """

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


def secondary_track_lengths_overlay_to_histogram(
    hdf5_path: str | Path | None = None,
    bins: int | Sequence[float] = 128,
    *,
    secondary_species: Sequence[str] | None = None,
    grouped_lengths_mm: dict[str, np.ndarray] | None = None,
    alpha: float = 0.45,
    log_scale: bool = True,
    x_max: float | None = None,
    output_path: str | Path | None = None,
    show: bool = False,
) -> tuple[Figure, Axes]:
    """Overlay secondary track-length histograms by species."""

    if not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must satisfy 0 < alpha <= 1.")
    if x_max is not None and x_max <= 0.0:
        raise ValueError("x_max must be positive when provided.")
    if grouped_lengths_mm is None:
        if hdf5_path is None:
            raise ValueError("hdf5_path is required when grouped_lengths_mm is not provided.")
        grouped_lengths_mm = secondary_track_lengths_by_species_mm(
            hdf5_path,
            secondary_species=secondary_species,
        )
    elif secondary_species is not None:
        raise ValueError(
            "secondary_species cannot be used when grouped_lengths_mm is provided."
        )
    if len(grouped_lengths_mm) == 0:
        raise ValueError("grouped_lengths_mm must contain at least one species.")

    all_lengths_mm = np.concatenate(list(grouped_lengths_mm.values()))
    if isinstance(bins, int) and x_max is not None:
        _, bin_edges = np.histogram(all_lengths_mm, bins=bins, range=(0.0, x_max))
    else:
        _, bin_edges = _histogram_counts(all_lengths_mm, bins=bins)

    fig, ax = plt.subplots(figsize=(8, 5.5))
    colors = overlay_histogram_colors(len(grouped_lengths_mm))
    for color, (species, lengths_mm) in zip(
        colors,
        grouped_lengths_mm.items(),
        strict=False,
    ):
        ax.hist(
            lengths_mm,
            bins=bin_edges,
            histtype="stepfilled",
            alpha=alpha,
            color=color,
            edgecolor=color,
            linewidth=1.0,
            label=f"{species} (n={len(lengths_mm)})",
        )

    ax.set_title("Secondary Track Lengths by Species")
    ax.set_xlabel("track length (mm)")
    ax.set_ylabel("counts")
    if log_scale:
        ax.set_yscale("log")
    if x_max is not None:
        ax.set_xlim(0.0, x_max)
    ax.legend()
    fig.tight_layout()

    save_and_maybe_show(fig, output_path=output_path, show=show)

    return fig, ax


def event_recoil_paths_to_image(
    hdf5_path: str | Path,
    gun_call_id: int,
    *,
    plane: str = "xy",
    output_path: str | Path | None = None,
    show: bool = False,
) -> tuple[Figure, Axes]:
    """Plot recoil paths and linked photon origins for one event in 2D."""

    secondaries = read_structured_dataset(hdf5_path, "secondaries")
    photons = read_structured_dataset(hdf5_path, "photons")
    secondary_required = {
        "gun_call_id",
        "secondary_track_id",
        "secondary_species",
        "secondary_origin_x_mm",
        "secondary_origin_y_mm",
        "secondary_origin_z_mm",
        SECONDARY_END_X_FIELD,
        SECONDARY_END_Y_FIELD,
        SECONDARY_END_Z_FIELD,
    }
    photon_required = {
        "gun_call_id",
        "secondary_track_id",
        "photon_origin_x_mm",
        "photon_origin_y_mm",
        "photon_origin_z_mm",
    }
    require_fields(secondaries, secondary_required, dataset_name="secondaries")
    require_fields(photons, photon_required, dataset_name="photons")

    end_field_by_axis = {
        "x": SECONDARY_END_X_FIELD,
        "y": SECONDARY_END_Y_FIELD,
        "z": SECONDARY_END_Z_FIELD,
    }
    axis_1, axis_2 = _projection_axes(plane)
    secondary_mask = np.asarray(secondaries["gun_call_id"], dtype=np.int64) == int(
        gun_call_id
    )
    photon_mask = np.asarray(photons["gun_call_id"], dtype=np.int64) == int(gun_call_id)
    event_secondaries = secondaries[secondary_mask]
    event_photons = photons[photon_mask]

    if len(event_secondaries) == 0:
        raise ValueError(f"No /secondaries rows found for gun_call_id={gun_call_id}.")

    fig, ax = plt.subplots(figsize=(7, 6))
    colors = overlay_histogram_colors(len(event_secondaries))
    all_x_mm: list[np.ndarray] = []
    all_y_mm: list[np.ndarray] = []
    species_labels = decode_species(event_secondaries["secondary_species"])
    secondary_track_ids = np.asarray(event_secondaries["secondary_track_id"], dtype=np.int32)
    photon_secondary_ids = np.asarray(event_photons["secondary_track_id"], dtype=np.int32)

    for color, species, secondary_track_id, row in zip(
        colors,
        species_labels,
        secondary_track_ids,
        event_secondaries,
        strict=False,
    ):
        origin_x = float(row[f"secondary_origin_{axis_1}_mm"])
        origin_y = float(row[f"secondary_origin_{axis_2}_mm"])
        end_x = float(row[end_field_by_axis[axis_1]])
        end_y = float(row[end_field_by_axis[axis_2]])
        line_is_finite = bool(
            np.isfinite(origin_x)
            and np.isfinite(origin_y)
            and np.isfinite(end_x)
            and np.isfinite(end_y)
        )
        if line_is_finite:
            all_x_mm.append(np.array([origin_x, end_x], dtype=float))
            all_y_mm.append(np.array([origin_y, end_y], dtype=float))

        secondary_photon_mask = photon_secondary_ids == secondary_track_id
        photon_x_mm = np.asarray(
            event_photons[f"photon_origin_{axis_1}_mm"][secondary_photon_mask],
            dtype=float,
        )
        photon_y_mm = np.asarray(
            event_photons[f"photon_origin_{axis_2}_mm"][secondary_photon_mask],
            dtype=float,
        )
        finite_photon_mask = np.isfinite(photon_x_mm) & np.isfinite(photon_y_mm)
        photon_x_mm = photon_x_mm[finite_photon_mask]
        photon_y_mm = photon_y_mm[finite_photon_mask]
        if photon_x_mm.size > 0:
            all_x_mm.append(photon_x_mm)
            all_y_mm.append(photon_y_mm)

        label = f"{species} #{secondary_track_id} (photons={len(photon_x_mm)})"
        if line_is_finite:
            ax.plot(
                [origin_x, end_x],
                [origin_y, end_y],
                color=color,
                linewidth=2.0,
                label=label,
            )
        if photon_x_mm.size > 0:
            ax.scatter(
                photon_x_mm,
                photon_y_mm,
                color=color,
                alpha=0.65,
                s=18.0,
                label=None if line_is_finite else label,
            )

    finite_x_values = [values for values in all_x_mm if values.size > 0]
    finite_y_values = [values for values in all_y_mm if values.size > 0]
    if not finite_x_values or not finite_y_values:
        raise ValueError(
            "No finite recoil-path or photon-origin coordinates were found "
            f"for gun_call_id={gun_call_id}."
        )
    x_values = np.concatenate(finite_x_values)
    y_values = np.concatenate(finite_y_values)
    x_min = float(np.min(x_values))
    x_max = float(np.max(x_values))
    y_min = float(np.min(y_values))
    y_max = float(np.max(y_values))
    x_pad = max(0.05 * (x_max - x_min), 0.5)
    y_pad = max(0.05 * (y_max - y_min), 0.5)

    ax.set_title(f"Recoil Paths and Photon Origins (event {gun_call_id}, {plane.lower()})")
    ax.set_xlabel(f"{axis_1} (mm)")
    ax.set_ylabel(f"{axis_2} (mm)")
    ax.set_xlim(x_min - x_pad, x_max + x_pad)
    ax.set_ylim(y_min - y_pad, y_max + y_pad)
    ax.set_aspect("equal", adjustable="box")
    ax.legend()
    fig.tight_layout()

    save_and_maybe_show(fig, output_path=output_path, show=show)

    return fig, ax


__all__ = [
    "ScintillationDecayComponent",
    "PhotonCreationDelayFitResult",
    "decay_model_bin_counts",
    "fit_photon_creation_delay_histogram",
    "photon_creation_delays_ns",
    "secondary_track_lengths_by_species_mm",
    "neutron_hits_to_image",
    "photon_origins_to_image",
    "photon_exit_to_image",
    "optical_interface_photons_to_image",
    "intensifier_photons_to_image",
    "photon_creation_delay_to_histogram",
    "secondary_track_lengths_overlay_to_histogram",
    "event_recoil_paths_to_image",
]
