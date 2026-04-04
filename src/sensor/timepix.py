"""Timepix sensor-stage parameter helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

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

