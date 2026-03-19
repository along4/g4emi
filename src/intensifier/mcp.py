"""Dual-stage MCP stage for the intensifier response pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from src.intensifier.models import McpEventBatch
from src.intensifier.models import McpParams
from src.intensifier.models import PhotoelectronBatch

if TYPE_CHECKING:
    from src.config.SimConfig import SimConfig


def mcp_params_from_sim_config(config: SimConfig) -> McpParams:
    """Build normalized MCP params from validated `SimConfig`."""

    intensifier = config.intensifier
    if intensifier is None:
        raise ValueError("`config.intensifier` is required for the MCP stage.")
    stage = intensifier.mcp
    return McpParams(
        stage1_mean_gain=float(stage.stage1_mean_gain),
        stage1_gain_shape=float(stage.stage1_gain_shape),
        stage2_mean_gain=float(stage.stage2_mean_gain),
        stage2_gain_shape=float(stage.stage2_gain_shape),
        gain_ref=float(stage.gain_ref),
        spread_sigma0_mm=float(stage.spread_sigma0_mm),
        spread_gain_exponent=float(stage.spread_gain_exponent),
    )


def sample_gamma_gain(
    mean_gain: float,
    gain_shape: float,
    size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample gamma-distributed gain values from mean and shape."""

    scale = mean_gain / gain_shape
    return rng.gamma(shape=gain_shape, scale=scale, size=size)


def compute_mcp_spread_sigma_mm(
    total_gain: np.ndarray,
    params: McpParams,
) -> np.ndarray:
    """Return gain-dependent MCP output spread in millimeters."""

    return params.spread_sigma0_mm * (total_gain / params.gain_ref) ** params.spread_gain_exponent


def convert_photoelectrons_to_mcp_events(
    photoelectrons: PhotoelectronBatch,
    params: McpParams,
    rng: np.random.Generator | None = None,
) -> McpEventBatch:
    """Convert photoelectron events into dual-stage MCP output events."""

    if rng is None:
        rng = np.random.default_rng()

    if len(photoelectrons) == 0:
        return McpEventBatch(
            source_photon_index=np.array([], dtype=np.int64),
            gun_call_id=np.array([], dtype=np.int64),
            primary_track_id=np.array([], dtype=np.int32),
            secondary_track_id=np.array([], dtype=np.int32),
            photon_track_id=np.array([], dtype=np.int32),
            x_mcp_mm=np.array([], dtype=np.float64),
            y_mcp_mm=np.array([], dtype=np.float64),
            time_mcp_ns=np.array([], dtype=np.float64),
            stage1_gain=np.array([], dtype=np.float64),
            stage2_gain=np.array([], dtype=np.float64),
            total_gain=np.array([], dtype=np.float64),
            wavelength_nm=np.array([], dtype=np.float64),
        )

    event_count = len(photoelectrons)
    stage1_gain = sample_gamma_gain(
        params.stage1_mean_gain,
        params.stage1_gain_shape,
        event_count,
        rng,
    )
    stage2_gain = sample_gamma_gain(
        params.stage2_mean_gain,
        params.stage2_gain_shape,
        event_count,
        rng,
    )
    total_gain = stage1_gain * stage2_gain
    spread_sigma_mm = compute_mcp_spread_sigma_mm(total_gain, params)

    x_mcp_mm = photoelectrons.x_pc_mm.copy()
    y_mcp_mm = photoelectrons.y_pc_mm.copy()
    nonzero_sigma = spread_sigma_mm > 0.0
    if np.any(nonzero_sigma):
        x_mcp_mm[nonzero_sigma] += rng.normal(
            loc=0.0,
            scale=spread_sigma_mm[nonzero_sigma],
            size=int(np.count_nonzero(nonzero_sigma)),
        )
        y_mcp_mm[nonzero_sigma] += rng.normal(
            loc=0.0,
            scale=spread_sigma_mm[nonzero_sigma],
            size=int(np.count_nonzero(nonzero_sigma)),
        )

    return McpEventBatch(
        source_photon_index=photoelectrons.source_photon_index,
        gun_call_id=photoelectrons.gun_call_id,
        primary_track_id=photoelectrons.primary_track_id,
        secondary_track_id=photoelectrons.secondary_track_id,
        photon_track_id=photoelectrons.photon_track_id,
        x_mcp_mm=x_mcp_mm,
        y_mcp_mm=y_mcp_mm,
        time_mcp_ns=photoelectrons.time_pc_ns.copy(),
        stage1_gain=stage1_gain,
        stage2_gain=stage2_gain,
        total_gain=total_gain,
        wavelength_nm=photoelectrons.wavelength_nm,
    )
