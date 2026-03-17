"""Event-level analysis helpers for recoil-path visualization."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from analysis.io import decode_species, read_structured_dataset, require_fields
from analysis.plotting import overlay_histogram_colors, save_and_maybe_show
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from src.common.hdf5_schema import (
    SECONDARY_END_X_FIELD,
    SECONDARY_END_Y_FIELD,
    SECONDARY_END_Z_FIELD,
)


def _projection_axes(plane: str) -> tuple[str, str]:
    """Return the in-plane axis labels for a requested 2D projection."""

    normalized = plane.strip().lower()
    if normalized not in {"xy", "xz", "yz"}:
        raise ValueError("plane must be one of: 'xy', 'xz', 'yz'.")
    return normalized[0], normalized[1]


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


__all__ = ["event_recoil_paths_to_image"]
