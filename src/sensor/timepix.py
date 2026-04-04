"""Timepix sensor-stage parameter helpers and geometry mapping."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from src.intensifier.models import IntensifierOutputBatch
from src.sensor.models import TimepixEventBatch
from src.sensor.models import TimepixParams

if TYPE_CHECKING:
    from src.config.SimConfig import SimConfig


def timepix_params_from_sim_config(config: SimConfig) -> TimepixParams:
    """Build normalized Timepix params from validated `SimConfig`."""

    sensor = config.sensor
    if sensor is None:
        raise ValueError("`config.sensor` is required for the Timepix stage.")
    stage = sensor.timepix
    return TimepixParams(
        pixels_x=int(stage.pixels_x),
        pixels_y=int(stage.pixels_y),
        pixel_pitch_mm=float(stage.pixel_pitch_mm),
        max_tot_ns=float(stage.max_tot_ns),
        dead_time_ns=float(stage.dead_time_ns),
    )


def compute_timepix_sensor_size_mm(params: TimepixParams) -> tuple[float, float]:
    """Return active Timepix width/height in millimeters."""

    return (
        float(params.pixels_x) * float(params.pixel_pitch_mm),
        float(params.pixels_y) * float(params.pixel_pitch_mm),
    )


def timepix_in_bounds_mask(
    intensifier_output: IntensifierOutputBatch,
    params: TimepixParams,
) -> np.ndarray:
    """Return a mask for intensifier events that fall on the centered Timepix area."""

    sensor_width_mm, sensor_height_mm = compute_timepix_sensor_size_mm(params)
    half_width_mm = sensor_width_mm / 2.0
    half_height_mm = sensor_height_mm / 2.0
    return (
        (intensifier_output.output_x_mm >= -half_width_mm)
        & (intensifier_output.output_x_mm < half_width_mm)
        & (intensifier_output.output_y_mm >= -half_height_mm)
        & (intensifier_output.output_y_mm < half_height_mm)
    )


def centered_mm_to_pixel_indices(
    x_mm: np.ndarray,
    y_mm: np.ndarray,
    params: TimepixParams,
) -> tuple[np.ndarray, np.ndarray]:
    """Map centered sensor-plane coordinates onto Timepix pixel indices."""

    sensor_width_mm, sensor_height_mm = compute_timepix_sensor_size_mm(params)
    x_pixel = np.floor((x_mm + sensor_width_mm / 2.0) / params.pixel_pitch_mm).astype(
        np.int32
    )
    y_pixel = np.floor((y_mm + sensor_height_mm / 2.0) / params.pixel_pitch_mm).astype(
        np.int32
    )
    return x_pixel, y_pixel


def map_intensifier_output_to_timepix_events(
    intensifier_output: IntensifierOutputBatch,
    params: TimepixParams,
) -> TimepixEventBatch:
    """Map centered intensifier output events onto the Timepix active area."""

    if len(intensifier_output) == 0:
        return TimepixEventBatch.empty()

    mask = timepix_in_bounds_mask(intensifier_output, params)
    if not np.any(mask):
        return TimepixEventBatch.empty()

    x_pixel, y_pixel = centered_mm_to_pixel_indices(
        intensifier_output.output_x_mm[mask],
        intensifier_output.output_y_mm[mask],
        params,
    )
    return TimepixEventBatch(
        source_photon_index=intensifier_output.source_photon_index[mask],
        gun_call_id=intensifier_output.gun_call_id[mask],
        primary_track_id=intensifier_output.primary_track_id[mask],
        secondary_track_id=intensifier_output.secondary_track_id[mask],
        photon_track_id=intensifier_output.photon_track_id[mask],
        x_pixel=x_pixel,
        y_pixel=y_pixel,
        event_time_ns=intensifier_output.output_time_ns[mask],
        signal_amplitude_arb=intensifier_output.signal_amplitude_arb[mask],
    )
