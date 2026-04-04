"""Timepix sensor-stage parameter helpers and geometry mapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from src.intensifier.models import IntensifierOutputBatch
from src.sensor.models import TimepixEventBatch
from src.sensor.models import TimepixHitBatch
from src.sensor.models import TimepixParams

if TYPE_CHECKING:
    from src.config.SimConfig import SimConfig


@dataclass(slots=True)
class _ActivePixelState:
    """Mutable per-pixel readout state while accumulating one hit row."""

    hit_index: int
    hit_end_time_ns: float


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


def timepix_in_bounds_mask(
    intensifier_output: IntensifierOutputBatch,
    params: TimepixParams,
) -> np.ndarray:
    """Return a mask for intensifier events that fall on the centered Timepix area."""

    half_width_mm = params.sensor_width_mm / 2.0
    half_height_mm = params.sensor_height_mm / 2.0
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

    x_pixel = np.floor((x_mm + params.sensor_width_mm / 2.0) / params.pixel_pitch_mm).astype(
        np.int32
    )
    y_pixel = np.floor((y_mm + params.sensor_height_mm / 2.0) / params.pixel_pitch_mm).astype(
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


def sort_timepix_events_by_time(events: TimepixEventBatch) -> TimepixEventBatch:
    """Return one Timepix event batch sorted by event time with stable ordering."""

    if len(events) == 0:
        return TimepixEventBatch.empty()

    order = np.argsort(events.event_time_ns, kind="stable")
    return TimepixEventBatch(
        source_photon_index=events.source_photon_index[order],
        gun_call_id=events.gun_call_id[order],
        primary_track_id=events.primary_track_id[order],
        secondary_track_id=events.secondary_track_id[order],
        photon_track_id=events.photon_track_id[order],
        x_pixel=events.x_pixel[order],
        y_pixel=events.y_pixel[order],
        event_time_ns=events.event_time_ns[order],
        signal_amplitude_arb=events.signal_amplitude_arb[order],
    )


def convert_timepix_events_to_hits(
    events: TimepixEventBatch,
    params: TimepixParams,
) -> TimepixHitBatch:
    """Apply per-pixel ToT and dead-time behavior to mapped Timepix events."""

    if len(events) == 0:
        return TimepixHitBatch.empty()

    sorted_events = sort_timepix_events_by_time(events)

    gun_call_id: list[int] = []
    primary_track_id: list[int] = []
    secondary_track_id: list[int] = []
    x_pixel: list[int] = []
    y_pixel: list[int] = []
    time_of_arrival_ns: list[float] = []
    time_over_threshold_ns: list[float] = []
    contribution_count: list[int] = []

    pixel_state: dict[tuple[int, int], _ActivePixelState] = {}

    for index in range(len(sorted_events)):
        pixel_key = (
            int(sorted_events.x_pixel[index]),
            int(sorted_events.y_pixel[index]),
        )
        event_time_ns = float(sorted_events.event_time_ns[index])
        tot_contribution_ns = min(
            float(sorted_events.signal_amplitude_arb[index]),
            float(params.max_tot_ns),
        )

        state = pixel_state.get(pixel_key)
        if state is not None:
            dead_time_end_ns = state.hit_end_time_ns + float(params.dead_time_ns)

            if event_time_ns < state.hit_end_time_ns:
                remaining_tot_ns = state.hit_end_time_ns - event_time_ns
                merged_tot_ns = min(
                    float(params.max_tot_ns),
                    remaining_tot_ns + tot_contribution_ns,
                )
                state.hit_end_time_ns = event_time_ns + merged_tot_ns
                time_over_threshold_ns[state.hit_index] = merged_tot_ns
                contribution_count[state.hit_index] += 1
                continue

            if event_time_ns < dead_time_end_ns:
                continue

        gun_call_id.append(int(sorted_events.gun_call_id[index]))
        primary_track_id.append(int(sorted_events.primary_track_id[index]))
        secondary_track_id.append(int(sorted_events.secondary_track_id[index]))
        x_pixel.append(pixel_key[0])
        y_pixel.append(pixel_key[1])
        time_of_arrival_ns.append(0.0)
        time_over_threshold_ns.append(tot_contribution_ns)
        contribution_count.append(1)

        pixel_state[pixel_key] = _ActivePixelState(
            hit_index=len(gun_call_id) - 1,
            hit_end_time_ns=event_time_ns + tot_contribution_ns,
        )

    return TimepixHitBatch(
        gun_call_id=np.asarray(gun_call_id, dtype=np.int64),
        primary_track_id=np.asarray(primary_track_id, dtype=np.int32),
        secondary_track_id=np.asarray(secondary_track_id, dtype=np.int32),
        x_pixel=np.asarray(x_pixel, dtype=np.int32),
        y_pixel=np.asarray(y_pixel, dtype=np.int32),
        time_of_arrival_ns=np.asarray(time_of_arrival_ns, dtype=np.float64),
        time_over_threshold_ns=np.asarray(time_over_threshold_ns, dtype=np.float64),
        contribution_count=np.asarray(contribution_count, dtype=np.int32),
    )
