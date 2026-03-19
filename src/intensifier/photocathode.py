"""Photocathode stage for the intensifier response pipeline.

This stage converts transported photons on the intensifier input plane into
photoelectron events using a wavelength-dependent quantum efficiency, an
overall collection efficiency, and optional transit-time spread.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

from src.intensifier.models import PhotocathodeParams
from src.intensifier.models import PhotoelectronBatch
from src.intensifier.models import TransportedPhotonBatch

if TYPE_CHECKING:
    from src.config.SimConfig import SimConfig


def photocathode_params_from_sim_config(config: SimConfig) -> PhotocathodeParams:
    """Build normalized photocathode params from validated `SimConfig`."""

    intensifier = config.intensifier
    if intensifier is None:
        raise ValueError("`config.intensifier` is required for the photocathode stage.")
    stage = intensifier.photocathode
    return PhotocathodeParams(
        qe_wavelength_nm=np.asarray(stage.qe_wavelength_nm, dtype=np.float64),
        qe_values=np.asarray(stage.qe_values, dtype=np.float64),
        collection_efficiency=float(stage.collection_efficiency),
        tts_sigma_ns=float(stage.tts_sigma_ns),
    )


def interpolate_qe(
    wavelength_nm: npt.ArrayLike,
    params: PhotocathodeParams,
) -> npt.NDArray[np.float64]:
    """Interpolate photocathode QE onto `wavelength_nm`.

    Values outside the configured wavelength range are treated as zero so the
    model does not silently extrapolate QE beyond the calibration range.
    """

    wavelengths = np.asarray(wavelength_nm, dtype=np.float64)
    if wavelengths.ndim != 1:
        raise ValueError("`wavelength_nm` must be a 1D array.")
    return np.interp(
        wavelengths,
        params.qe_wavelength_nm,
        params.qe_values,
        left=0.0,
        right=0.0,
    )


def convert_photons_to_photoelectrons(
    photons: TransportedPhotonBatch,
    params: PhotocathodeParams,
    rng: np.random.Generator | None = None,
) -> PhotoelectronBatch:
    """Convert transported photons into photoelectron events.

    Detection probability per photon is:

    `p_detect = QE(lambda) * collection_efficiency`

    Timing jitter is modeled as a zero-mean Gaussian with width
    `params.tts_sigma_ns`.
    """

    if rng is None:
        rng = np.random.default_rng()

    if len(photons) == 0:
        return PhotoelectronBatch.empty()

    qe = interpolate_qe(photons.wavelength_nm, params)
    detection_probability = np.clip(qe * params.collection_efficiency, 0.0, 1.0)
    detected_mask = rng.random(len(photons)) < detection_probability

    detected_times = photons.time_ns[detected_mask].copy()
    if params.tts_sigma_ns > 0.0 and detected_times.size > 0:
        detected_times += rng.normal(
            loc=0.0,
            scale=params.tts_sigma_ns,
            size=detected_times.size,
        )

    return PhotoelectronBatch(
        source_photon_index=photons.source_photon_index[detected_mask],
        gun_call_id=photons.gun_call_id[detected_mask],
        primary_track_id=photons.primary_track_id[detected_mask],
        secondary_track_id=photons.secondary_track_id[detected_mask],
        photon_track_id=photons.photon_track_id[detected_mask],
        x_pc_mm=photons.x_mm[detected_mask],
        y_pc_mm=photons.y_mm[detected_mask],
        time_pc_ns=detected_times,
        wavelength_nm=photons.wavelength_nm[detected_mask],
    )
