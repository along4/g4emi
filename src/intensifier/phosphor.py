"""Phosphor stage for the intensifier response pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from src.intensifier.models import IntensifierOutputBatch
from src.intensifier.models import McpEventBatch
from src.intensifier.models import PhosphorParams

if TYPE_CHECKING:
    from src.config.SimConfig import SimConfig


def phosphor_params_from_sim_config(config: SimConfig) -> PhosphorParams:
    """Build normalized phosphor params from validated `SimConfig`."""

    intensifier = config.intensifier
    if intensifier is None:
        raise ValueError("`config.intensifier` is required for the phosphor stage.")
    stage = intensifier.phosphor
    return PhosphorParams(
        phosphor_gain=float(stage.phosphor_gain),
        decay_fast_ns=float(stage.decay_fast_ns),
        decay_slow_ns=float(stage.decay_slow_ns),
        fast_fraction=float(stage.fast_fraction),
        psf_sigma_mm=float(stage.psf_sigma_mm),
    )


def sample_phosphor_delay_ns(
    size: int,
    params: PhosphorParams,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample phosphor delays from a fast/slow exponential mixture."""

    if size < 0:
        raise ValueError("`size` must be non-negative.")
    if size == 0:
        return np.array([], dtype=np.float64)

    use_fast = rng.random(size) < params.fast_fraction
    delays = np.empty(size, dtype=np.float64)
    fast_count = int(np.count_nonzero(use_fast))
    slow_count = size - fast_count

    if fast_count > 0:
        delays[use_fast] = rng.exponential(
            scale=params.decay_fast_ns,
            size=fast_count,
        )
    if slow_count > 0:
        delays[~use_fast] = rng.exponential(
            scale=params.decay_slow_ns,
            size=slow_count,
        )
    return delays


def convert_mcp_events_to_intensifier_output(
    mcp_events: McpEventBatch,
    params: PhosphorParams,
    rng: np.random.Generator | None = None,
) -> IntensifierOutputBatch:
    """Convert MCP events into final intensifier output events."""

    if rng is None:
        rng = np.random.default_rng()

    if len(mcp_events) == 0:
        return IntensifierOutputBatch.empty()

    event_count = len(mcp_events)
    delays_ns = sample_phosphor_delay_ns(event_count, params, rng)
    output_x_mm = mcp_events.x_mcp_mm.copy()
    output_y_mm = mcp_events.y_mcp_mm.copy()

    if params.psf_sigma_mm > 0.0:
        output_x_mm += rng.normal(
            loc=0.0,
            scale=params.psf_sigma_mm,
            size=event_count,
        )
        output_y_mm += rng.normal(
            loc=0.0,
            scale=params.psf_sigma_mm,
            size=event_count,
        )

    return IntensifierOutputBatch(
        source_photon_index=mcp_events.source_photon_index,
        gun_call_id=mcp_events.gun_call_id,
        primary_track_id=mcp_events.primary_track_id,
        secondary_track_id=mcp_events.secondary_track_id,
        photon_track_id=mcp_events.photon_track_id,
        output_x_mm=output_x_mm,
        output_y_mm=output_y_mm,
        output_time_ns=mcp_events.time_mcp_ns + delays_ns,
        signal_amplitude_arb=params.phosphor_gain * mcp_events.total_gain,
        total_gain=mcp_events.total_gain,
        wavelength_nm=mcp_events.wavelength_nm,
    )
