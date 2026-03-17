"""Timing analysis helpers for photon creation delays and decay fits."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from analysis.io import read_structured_dataset, require_fields
from analysis.plotting import plot_histogram_1d
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from src.common.hdf5_schema import PRIMARY_INTERACTION_TIME_FIELD

try:
    from scipy.optimize import least_squares
except ModuleNotFoundError:
    least_squares = None


@dataclass(frozen=True)
class ScintillationDecayComponent:
    """One exponential decay component used for timing models."""

    time_constant_ns: float
    yield_fraction: float


@dataclass
class PhotonCreationDelayFitResult:
    """Three-component exponential fit summary for photon creation delays."""

    components: tuple[ScintillationDecayComponent, ...]
    observed_counts: np.ndarray
    fitted_counts: np.ndarray
    bin_edges_ns: np.ndarray
    rmse_counts: float


def _histogram_counts(
    values: np.ndarray,
    bins: int | Sequence[float],
) -> tuple[np.ndarray, np.ndarray]:
    """Build a 1D histogram and corresponding bin edges."""

    if values.size == 0:
        raise ValueError("No values available to plot.")
    return np.histogram(values, bins=bins)


def photon_creation_delays_ns(hdf5_path: str | Path) -> np.ndarray:
    """Return finite non-negative photon creation delays in nanoseconds."""

    primaries = read_structured_dataset(hdf5_path, "primaries")
    photons = read_structured_dataset(hdf5_path, "photons")
    primary_required = {"gun_call_id", "primary_track_id"}
    photon_required = {"gun_call_id", "primary_track_id", "photon_creation_time_ns"}
    require_fields(primaries, primary_required, dataset_name="primaries")
    require_fields(photons, photon_required, dataset_name="photons")

    key_dtype = np.dtype(
        [
            ("gun_call_id", np.int64),
            ("primary_track_id", np.int32),
        ]
    )
    primary_keys = np.empty(len(primaries), dtype=key_dtype)
    primary_keys["gun_call_id"] = np.asarray(primaries["gun_call_id"], dtype=np.int64)
    primary_keys["primary_track_id"] = np.asarray(
        primaries["primary_track_id"],
        dtype=np.int32,
    )
    photon_keys = np.empty(len(photons), dtype=key_dtype)
    photon_keys["gun_call_id"] = np.asarray(photons["gun_call_id"], dtype=np.int64)
    photon_keys["primary_track_id"] = np.asarray(
        photons["primary_track_id"],
        dtype=np.int32,
    )

    sort_idx = np.argsort(primary_keys, order=("gun_call_id", "primary_track_id"))
    sorted_primary_keys = primary_keys[sort_idx]
    sorted_interaction_times_ns = np.asarray(
        primaries[PRIMARY_INTERACTION_TIME_FIELD],
        dtype=float,
    )[sort_idx]
    photon_creation_times_ns = np.asarray(photons["photon_creation_time_ns"], dtype=float)

    match_idx = np.searchsorted(sorted_primary_keys, photon_keys, side="left")
    in_range_mask = match_idx < len(sorted_primary_keys)
    matched_mask = np.zeros(len(photons), dtype=bool)
    if np.any(in_range_mask):
        matched_mask[in_range_mask] = (
            sorted_primary_keys[match_idx[in_range_mask]] == photon_keys[in_range_mask]
        )

    if not np.any(matched_mask):
        raise ValueError(
            "No finite photon creation delays could be computed from the HDF5 data."
        )

    matched_interaction_times_ns = sorted_interaction_times_ns[match_idx[matched_mask]]
    matched_creation_times_ns = photon_creation_times_ns[matched_mask]
    finite_mask = np.isfinite(matched_interaction_times_ns) & np.isfinite(
        matched_creation_times_ns
    )
    delay_array = matched_creation_times_ns[finite_mask] - matched_interaction_times_ns[
        finite_mask
    ]
    delay_array = delay_array[delay_array >= 0.0]
    if delay_array.size == 0:
        raise ValueError(
            "No finite photon creation delays could be computed from the HDF5 data."
        )
    return delay_array


def decay_model_bin_counts(
    bin_edges_ns: Sequence[float],
    total_count: float,
    components: Sequence[ScintillationDecayComponent],
) -> np.ndarray:
    """Return expected histogram counts for a decay-component mixture."""

    edges = np.asarray(bin_edges_ns, dtype=float)
    if edges.ndim != 1 or edges.size < 2:
        raise ValueError("bin_edges_ns must be a 1D sequence with at least 2 entries.")
    if total_count <= 0.0:
        raise ValueError("total_count must be positive.")

    amplitudes, taus = _component_amplitudes_and_taus(
        components,
        total_count=total_count,
        validate_total_yield=True,
    )

    active_mask = amplitudes > 0.0
    taus = np.where(active_mask, taus, 1.0)
    left_edges = edges[:-1]
    right_edges = edges[1:]
    return np.sum(
        amplitudes[None, :]
        * (
            np.exp(-left_edges[:, None] / taus[None, :])
            - np.exp(-right_edges[:, None] / taus[None, :])
        ),
        axis=1,
    )


def _component_amplitudes_and_taus(
    components: Sequence[ScintillationDecayComponent],
    *,
    total_count: float,
    validate_total_yield: bool,
) -> tuple[np.ndarray, np.ndarray]:
    """Validate decay components and convert them into amplitudes/times."""

    component_list = list(components)
    if len(component_list) != 3:
        raise ValueError("Exactly 3 decay components are required.")

    yields = np.asarray(
        [float(component.yield_fraction) for component in component_list],
        dtype=float,
    )
    taus = np.asarray(
        [float(component.time_constant_ns) for component in component_list],
        dtype=float,
    )
    if not np.isfinite(yields).all() or not np.isfinite(taus).all():
        raise ValueError("Decay components must be finite.")
    if np.any(yields < 0.0):
        raise ValueError("Yield fractions must be non-negative.")
    active_mask = yields > 0.0
    if np.any(taus[active_mask] <= 0.0):
        raise ValueError("Active decay time constants must be positive.")

    total_yield = float(np.sum(yields))
    if validate_total_yield and total_yield <= 0.0:
        raise ValueError("At least one decay component must have positive yield.")
    normalized_yields = yields / total_yield
    amplitudes = float(total_count) * normalized_yields
    return amplitudes, taus


def fit_photon_creation_delay_histogram(
    hdf5_path: str | Path,
    bins: int | Sequence[float] = 256,
    *,
    initial_components: Sequence[ScintillationDecayComponent] | None = None,
) -> PhotonCreationDelayFitResult:
    """Fit a 3-component exponential mixture to the photon-creation histogram."""

    if least_squares is None:
        raise ModuleNotFoundError(
            "scipy is required for timing fits. Install project dependencies with "
            "`pixi install`."
        )

    delays_ns = photon_creation_delays_ns(hdf5_path)
    observed_counts, bin_edges = _histogram_counts(delays_ns, bins=bins)
    total_count = float(np.sum(observed_counts))
    if total_count <= 0.0:
        raise ValueError("Timing histogram is empty; cannot perform fit.")

    max_delay_ns = float(bin_edges[-1])
    min_tau_ns = max(max_delay_ns / 1.0e5, 1.0e-3)
    max_tau_ns = max(max_delay_ns * 5.0, 1.0)
    if initial_components is not None:
        amplitude_guess, tau_guess = _component_amplitudes_and_taus(
            initial_components,
            total_count=total_count,
            validate_total_yield=True,
        )
    else:
        amplitude_guess = total_count * np.array([0.7, 0.2, 0.1], dtype=float)
        tau_guess = np.array(
            [
                max(max_delay_ns / 80.0, 0.2),
                max(max_delay_ns / 12.0, 1.0),
                max(max_delay_ns / 2.0, 5.0),
            ],
            dtype=float,
        )

    tau_guess = np.clip(tau_guess, min_tau_ns, max_tau_ns)
    amplitude_guess = np.clip(amplitude_guess, 1.0e-6, max(total_count, 1.0))

    def residuals(params: np.ndarray) -> np.ndarray:
        amplitudes = params[:3]
        taus = params[3:]
        model_counts = np.sum(
            amplitudes[None, :]
            * (
                np.exp(-bin_edges[:-1, None] / taus[None, :])
                - np.exp(-bin_edges[1:, None] / taus[None, :])
            ),
            axis=1,
        )
        weights = np.sqrt(np.maximum(observed_counts, 1.0))
        return (model_counts - observed_counts) / weights

    initial_params = np.concatenate([amplitude_guess, tau_guess])
    lower_bounds = np.concatenate(
        [np.full(3, 1.0e-12, dtype=float), np.full(3, min_tau_ns, dtype=float)]
    )
    upper_bounds = np.concatenate(
        [
            np.full(3, max(total_count * 2.0, 1.0), dtype=float),
            np.full(3, max_tau_ns, dtype=float),
        ]
    )

    result = least_squares(
        residuals,
        initial_params,
        bounds=(lower_bounds, upper_bounds),
        max_nfev=20000,
    )
    if not result.success:
        raise RuntimeError(f"Timing fit failed: {result.message}")

    fitted_amplitudes = np.asarray(result.x[:3], dtype=float)
    fitted_taus = np.asarray(result.x[3:], dtype=float)
    order = np.argsort(fitted_taus)
    fitted_amplitudes = fitted_amplitudes[order]
    fitted_taus = fitted_taus[order]
    fitted_counts = np.sum(
        fitted_amplitudes[None, :]
        * (
            np.exp(-bin_edges[:-1, None] / fitted_taus[None, :])
            - np.exp(-bin_edges[1:, None] / fitted_taus[None, :])
        ),
        axis=1,
    )

    amplitude_total = float(np.sum(fitted_amplitudes))
    yield_fractions = fitted_amplitudes / amplitude_total
    components = tuple(
        ScintillationDecayComponent(
            time_constant_ns=float(time_constant_ns),
            yield_fraction=float(yield_fraction),
        )
        for time_constant_ns, yield_fraction in zip(
            fitted_taus,
            yield_fractions,
            strict=False,
        )
    )
    rmse_counts = float(np.sqrt(np.mean(np.square(fitted_counts - observed_counts))))
    return PhotonCreationDelayFitResult(
        components=components,
        observed_counts=np.asarray(observed_counts, dtype=float),
        fitted_counts=np.asarray(fitted_counts, dtype=float),
        bin_edges_ns=np.asarray(bin_edges, dtype=float),
        rmse_counts=rmse_counts,
    )


def photon_creation_delay_to_histogram(
    hdf5_path: str | Path,
    bins: int | Sequence[float] = 256,
    *,
    log_scale: bool = True,
    output_path: str | Path | None = None,
    show: bool = False,
) -> tuple[Figure, Axes]:
    """Plot photon creation delay relative to primary scintillator interaction."""

    delay_array = photon_creation_delays_ns(hdf5_path)
    _, bin_edges = _histogram_counts(delay_array, bins=bins)
    return plot_histogram_1d(
        delay_array,
        bin_edges=bin_edges,
        title="Photon Creation Delay from Primary Interaction",
        x_label="delay (ns)",
        log_scale=log_scale,
        output_path=output_path,
        show=show,
    )


__all__ = [
    "ScintillationDecayComponent",
    "PhotonCreationDelayFitResult",
    "decay_model_bin_counts",
    "fit_photon_creation_delay_histogram",
    "photon_creation_delays_ns",
    "photon_creation_delay_to_histogram",
]
