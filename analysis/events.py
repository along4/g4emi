"""Event-level analysis helpers for recoil-path visualization."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from analysis.io import decode_species, read_structured_dataset, require_fields
from analysis.plotting import save_and_maybe_show
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from src.common.hdf5_schema import DATASET_TRANSPORTED_PHOTONS
from src.common.hdf5_schema import (
    PHOTON_SCINT_EXIT_X_FIELD,
    PHOTON_SCINT_EXIT_Y_FIELD,
    PHOTON_SCINT_EXIT_Z_FIELD,
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


def _normalize_secondary_species_label(species: str) -> str:
    """Normalize common secondary-species aliases to one comparison label."""

    normalized = species.strip().lower()
    alias_map = {
        "proton": "p",
        "p": "p",
        "neutron": "n",
        "n": "n",
        "gamma": "g",
        "photon": "g",
        "g": "g",
        "alpha": "a",
        "a": "a",
        "deuterium": "deuteron",
        "d": "deuteron",
        "deuteron": "deuteron",
        "positron": "positron",
        "electron": "electron",
    }
    return alias_map.get(normalized, normalized)


def _set_hover_text(artist: object, text: str) -> None:
    """Attach hover text to a Matplotlib artist for optional interactive use."""

    setattr(artist, "_hover_text", text)
    if hasattr(artist, "set_picker"):
        artist.set_picker(True)


def gun_call_ids_with_secondary_species(
    hdf5_path: str | Path,
    secondary_species: str | None = None,
) -> np.ndarray:
    """Return sorted event IDs that contain secondaries matching the species filter."""

    secondaries = read_structured_dataset(hdf5_path, "secondaries")
    require_fields(
        secondaries,
        {"gun_call_id", "secondary_species"},
        dataset_name="secondaries",
    )

    gun_call_ids = np.asarray(secondaries["gun_call_id"], dtype=np.int64)
    if secondary_species is None:
        return np.unique(gun_call_ids)

    requested_species = _normalize_secondary_species_label(secondary_species)
    if requested_species == "":
        raise ValueError("secondary_species must not be empty when provided.")

    species = np.array(
        [_normalize_secondary_species_label(value) for value in decode_species(secondaries["secondary_species"])],
        dtype=object,
    )
    return np.unique(gun_call_ids[species == requested_species])


def random_gun_call_id(
    hdf5_path: str | Path,
    *,
    secondary_species: str | None = None,
    seed: int | None = None,
) -> int:
    """Choose one event ID uniformly from the available matching secondaries."""

    candidates = gun_call_ids_with_secondary_species(
        hdf5_path,
        secondary_species=secondary_species,
    )
    if candidates.size == 0:
        if secondary_species is None:
            raise ValueError("No event IDs were found in /secondaries.")
        raise ValueError(
            f"No event IDs were found with secondary_species={secondary_species!r}."
        )

    rng = np.random.default_rng(seed)
    return int(candidates[rng.integers(0, candidates.size)])


def event_recoil_paths_to_image(
    hdf5_path: str | Path,
    gun_call_id: int,
    *,
    plane: str = "xy",
    transport_hdf5_path: str | Path | None = None,
    output_path: str | Path | None = None,
    show: bool = False,
) -> tuple[Figure, Axes]:
    """Plot recoil paths and linked photon origins for one event in 2D."""

    primaries = read_structured_dataset(hdf5_path, "primaries")
    secondaries = read_structured_dataset(hdf5_path, "secondaries")
    photons = read_structured_dataset(hdf5_path, "photons")
    primary_required = {"gun_call_id", "primary_species", "primary_x_mm", "primary_y_mm"}
    secondary_required = {
        "gun_call_id",
        "secondary_track_id",
        "secondary_species",
        "secondary_origin_x_mm",
        "secondary_origin_y_mm",
        "secondary_origin_z_mm",
        "secondary_origin_energy_MeV",
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
        PHOTON_SCINT_EXIT_X_FIELD,
        PHOTON_SCINT_EXIT_Y_FIELD,
        PHOTON_SCINT_EXIT_Z_FIELD,
    }
    require_fields(primaries, primary_required, dataset_name="primaries")
    require_fields(secondaries, secondary_required, dataset_name="secondaries")
    require_fields(photons, photon_required, dataset_name="photons")

    end_field_by_axis = {
        "x": SECONDARY_END_X_FIELD,
        "y": SECONDARY_END_Y_FIELD,
        "z": SECONDARY_END_Z_FIELD,
    }
    axis_1, axis_2 = _projection_axes(plane)
    primary_mask = np.asarray(primaries["gun_call_id"], dtype=np.int64) == int(gun_call_id)
    secondary_mask = np.asarray(secondaries["gun_call_id"], dtype=np.int64) == int(
        gun_call_id
    )
    photon_mask = np.asarray(photons["gun_call_id"], dtype=np.int64) == int(gun_call_id)
    event_primaries = primaries[primary_mask]
    event_secondaries = secondaries[secondary_mask]
    event_photons = photons[photon_mask]
    event_photon_indices = np.flatnonzero(photon_mask)

    if len(event_secondaries) == 0:
        raise ValueError(f"No /secondaries rows found for gun_call_id={gun_call_id}.")

    transport_reached_mask: np.ndarray | None = None
    if transport_hdf5_path is not None:
        transported = read_structured_dataset(transport_hdf5_path, DATASET_TRANSPORTED_PHOTONS)
        require_fields(
            transported,
            {"source_photon_index"},
            dataset_name=DATASET_TRANSPORTED_PHOTONS,
        )
        source_indices = np.asarray(transported["source_photon_index"], dtype=np.int64)
        reached_lookup = {int(source_index): True for source_index in source_indices}
        transport_reached_mask = np.array(
            [reached_lookup.get(int(index), False) for index in event_photon_indices],
            dtype=bool,
        )

    fig, ax = plt.subplots(figsize=(7, 6))
    all_x_mm: list[np.ndarray] = []
    all_y_mm: list[np.ndarray] = []
    species_labels = decode_species(event_secondaries["secondary_species"])
    secondary_track_ids = np.asarray(event_secondaries["secondary_track_id"], dtype=np.int32)
    photon_secondary_ids = np.asarray(event_photons["secondary_track_id"], dtype=np.int32)
    secondary_colors = plt.cm.tab10(np.linspace(0.0, 1.0, max(len(event_secondaries), 2)))

    if (
        len(event_primaries) > 0
        and f"primary_{axis_1}_mm" in (event_primaries.dtype.names or ())
        and f"primary_{axis_2}_mm" in (event_primaries.dtype.names or ())
    ):
        primary_x_mm = np.asarray(event_primaries[f"primary_{axis_1}_mm"], dtype=float)
        primary_y_mm = np.asarray(event_primaries[f"primary_{axis_2}_mm"], dtype=float)
        neutron_mask = np.isin(
            decode_species(event_primaries["primary_species"]),
            np.array(["n", "neutron"], dtype=object),
        )
        finite_primary_mask = np.isfinite(primary_x_mm) & np.isfinite(primary_y_mm)
        primary_plot_mask = finite_primary_mask & neutron_mask
        if np.any(primary_plot_mask):
            all_x_mm.append(primary_x_mm[primary_plot_mask])
            all_y_mm.append(primary_y_mm[primary_plot_mask])
            neutron_artist = ax.scatter(
                primary_x_mm[primary_plot_mask],
                primary_y_mm[primary_plot_mask],
                marker="x",
                color="black",
                s=80.0,
                linewidths=1.8,
                label="Neutron hit",
                zorder=5,
            )
            _set_hover_text(
                neutron_artist,
                "Neutron hit\n"
                f"event={gun_call_id}\n"
                f"{axis_1}={primary_x_mm[primary_plot_mask][0]:.3f} mm\n"
                f"{axis_2}={primary_y_mm[primary_plot_mask][0]:.3f} mm",
            )

    for color, species, secondary_track_id, row in zip(
        secondary_colors,
        species_labels,
        secondary_track_ids,
        event_secondaries,
        strict=False,
    ):
        origin_x = float(row[f"secondary_origin_{axis_1}_mm"])
        origin_y = float(row[f"secondary_origin_{axis_2}_mm"])
        origin_energy_mev = float(row["secondary_origin_energy_MeV"])
        end_x = float(row[end_field_by_axis[axis_1]])
        end_y = float(row[end_field_by_axis[axis_2]])
        energy_label = (
            f"{origin_energy_mev:.3f} MeV" if np.isfinite(origin_energy_mev) else "unknown energy"
        )
        line_is_finite = bool(
            np.isfinite(origin_x)
            and np.isfinite(origin_y)
            and np.isfinite(end_x)
            and np.isfinite(end_y)
        )
        if line_is_finite:
            all_x_mm.append(np.array([origin_x, end_x], dtype=float))
            all_y_mm.append(np.array([origin_y, end_y], dtype=float))
            line_artist = ax.plot(
                [origin_x, end_x],
                [origin_y, end_y],
                color=color,
                linewidth=1.8,
                alpha=0.9,
                label=f"{species} #{secondary_track_id}, {energy_label}",
                zorder=2,
            )[0]
            _set_hover_text(
                line_artist,
                f"{species} #{secondary_track_id}\n"
                f"energy={energy_label}\n"
                f"origin: ({origin_x:.3f}, {origin_y:.3f}) mm\n"
                f"end: ({end_x:.3f}, {end_y:.3f}) mm",
            )
            origin_artist = ax.scatter(
                [origin_x],
                [origin_y],
                color=[color],
                marker="o",
                s=36.0,
                edgecolors="black",
                linewidths=0.5,
                label=None,
                zorder=3,
            )
            _set_hover_text(
                origin_artist,
                f"{species} #{secondary_track_id} origin\n"
                f"{axis_1}={origin_x:.3f} mm\n"
                f"{axis_2}={origin_y:.3f} mm",
            )
            end_artist = ax.scatter(
                [end_x],
                [end_y],
                color=[color],
                marker="s",
                s=34.0,
                edgecolors="black",
                linewidths=0.5,
                label=None,
                zorder=3,
            )
            _set_hover_text(
                end_artist,
                f"{species} #{secondary_track_id} end\n"
                f"{axis_1}={end_x:.3f} mm\n"
                f"{axis_2}={end_y:.3f} mm",
            )

        secondary_photon_mask = photon_secondary_ids == secondary_track_id
        emitted_photon_count = int(np.count_nonzero(secondary_photon_mask))
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
        line_label = (
            f"{species} #{secondary_track_id}, {energy_label}, "
            f"enter-lens={emitted_photon_count}"
        )
        if line_is_finite:
            line_artist.set_label(line_label)
            _set_hover_text(
                line_artist,
                f"{species} #{secondary_track_id}\n"
                f"energy={energy_label}\n"
                f"enter-lens photons={emitted_photon_count}\n"
                f"origin: ({origin_x:.3f}, {origin_y:.3f}) mm\n"
                f"end: ({end_x:.3f}, {end_y:.3f}) mm",
            )

    photon_x_all = np.asarray(event_photons[f"photon_origin_{axis_1}_mm"], dtype=float)
    photon_y_all = np.asarray(event_photons[f"photon_origin_{axis_2}_mm"], dtype=float)
    finite_photon_mask = np.isfinite(photon_x_all) & np.isfinite(photon_y_all)
    photon_x_all = photon_x_all[finite_photon_mask]
    photon_y_all = photon_y_all[finite_photon_mask]
    photon_reached_mask = (
        transport_reached_mask[finite_photon_mask]
        if transport_reached_mask is not None
        else np.zeros(photon_x_all.shape[0], dtype=bool)
    )
    photon_exit_x_all = np.asarray(event_photons[f"photon_scint_exit_{axis_1}_mm"], dtype=float)
    photon_exit_y_all = np.asarray(event_photons[f"photon_scint_exit_{axis_2}_mm"], dtype=float)
    finite_exit_mask = np.isfinite(photon_exit_x_all) & np.isfinite(photon_exit_y_all)
    photon_exit_x_all = photon_exit_x_all[finite_exit_mask]
    photon_exit_y_all = photon_exit_y_all[finite_exit_mask]
    photon_exit_reached_mask = (
        transport_reached_mask[finite_exit_mask]
        if transport_reached_mask is not None
        else np.zeros(photon_exit_x_all.shape[0], dtype=bool)
    )
    if photon_exit_x_all.size > 0:
        all_x_mm.append(photon_exit_x_all)
        all_y_mm.append(photon_exit_y_all)

    unreached_mask = ~photon_reached_mask
    if np.any(unreached_mask):
        unreached_artist = ax.scatter(
            photon_x_all[unreached_mask],
            photon_y_all[unreached_mask],
            color="#d95f02",
            alpha=0.22,
            s=18.0,
            label=(
                "Photon origins (missed intensifier)"
                if transport_reached_mask is not None
                else "Photon origins"
            ),
            zorder=1,
        )
        _set_hover_text(
            unreached_artist,
            "Photon origins\n"
            f"class={'missed intensifier' if transport_reached_mask is not None else 'all'}\n"
            f"count={int(np.count_nonzero(unreached_mask))}",
        )
    exit_unreached_mask = ~photon_exit_reached_mask
    if np.any(exit_unreached_mask):
        exit_unreached_artist = ax.scatter(
            photon_exit_x_all[exit_unreached_mask],
            photon_exit_y_all[exit_unreached_mask],
            color="#d95f02",
            alpha=0.45,
            s=52.0,
            marker="^",
            label=(
                "Photon exits (missed intensifier)"
                if transport_reached_mask is not None
                else "Photon exits"
            ),
            zorder=1,
        )
        _set_hover_text(
            exit_unreached_artist,
            "Photon exits\n"
            f"class={'missed intensifier' if transport_reached_mask is not None else 'all'}\n"
            f"count={int(np.count_nonzero(exit_unreached_mask))}",
        )
    if np.any(photon_reached_mask):
        reached_artist = ax.scatter(
            photon_x_all[photon_reached_mask],
            photon_y_all[photon_reached_mask],
            color="#1b9e77",
            alpha=0.32,
            s=22.0,
            label="Photon origins (reached intensifier)",
            zorder=1,
        )
        _set_hover_text(
            reached_artist,
            "Photon origins\n"
            "class=reached intensifier\n"
            f"count={int(np.count_nonzero(photon_reached_mask))}",
        )
    if np.any(photon_exit_reached_mask):
        exit_reached_artist = ax.scatter(
            photon_exit_x_all[photon_exit_reached_mask],
            photon_exit_y_all[photon_exit_reached_mask],
            color="#1b9e77",
            alpha=0.55,
            s=58.0,
            marker="^",
            label="Photon exits (reached intensifier)",
            zorder=1,
        )
        _set_hover_text(
            exit_reached_artist,
            "Photon exits\n"
            "class=reached intensifier\n"
            f"count={int(np.count_nonzero(photon_exit_reached_mask))}",
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

    ax.set_title(f"Neutron Event View (event {gun_call_id}, {plane.lower()})")
    ax.set_xlabel(f"{axis_1} (mm)")
    ax.set_ylabel(f"{axis_2} (mm)")
    ax.set_xlim(x_min - x_pad, x_max + x_pad)
    ax.set_ylim(y_min - y_pad, y_max + y_pad)
    ax.set_aspect("equal", adjustable="box")
    ax.legend(loc="best")
    fig.tight_layout()
    save_and_maybe_show(fig, output_path=output_path, show=show)
    return fig, ax


__all__ = [
    "event_recoil_paths_to_image",
    "gun_call_ids_with_secondary_species",
    "random_gun_call_id",
]
