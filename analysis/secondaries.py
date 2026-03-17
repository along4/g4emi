"""Secondary-particle analysis helpers.

This module should own:
- secondary track-length extraction
- grouping by secondary species
- secondary overlay histogram rendering

This module should not own:
- timing fits
- spatial quick-look plots
- event recoil visualization
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

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
        if all_lengths_mm.size == 0:
            raise ValueError("No values available to plot.")
        _, bin_edges = np.histogram(all_lengths_mm, bins=bins)

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


__all__ = [
    "secondary_track_lengths_by_species_mm",
    "secondary_track_lengths_overlay_to_histogram",
]
