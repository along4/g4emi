"""High-level intensifier pipeline orchestration."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import TYPE_CHECKING

import numpy as np

from src.common.logger import get_logger
from src.common.logger import log_stage
from src.intensifier.io import load_transported_photon_batch_from_sim_config
from src.intensifier.io import write_intensifier_output_hdf5
from src.intensifier.mcp import convert_photoelectrons_to_mcp_events
from src.intensifier.mcp import mcp_params_from_sim_config
from src.intensifier.models import IntensifierOutputBatch
from src.intensifier.models import IntensifierParams
from src.intensifier.models import TransportedPhotonBatch
from src.intensifier.phosphor import convert_mcp_events_to_intensifier_output
from src.intensifier.phosphor import phosphor_params_from_sim_config
from src.intensifier.photocathode import convert_photons_to_photoelectrons
from src.intensifier.photocathode import photocathode_params_from_sim_config

if TYPE_CHECKING:
    from src.config.SimConfig import SimConfig


_DEFAULT_INTENSIFIER_CHUNK_ROWS = 250_000


def _write_compute_progress(current: int, total: int) -> None:
    """Render a simple in-terminal progress bar for intensifier compute work."""

    if total <= 0:
        return
    clamped = min(current, total)
    width = 30
    fraction = clamped / total
    filled = int(width * fraction)
    bar = f"[{'#' * filled}{'-' * (width - filled)}]"
    percent = int(fraction * 100)
    sys.stderr.write(
        f"\rIntensifier compute {bar} {percent:3d}% ({clamped}/{total} photons)"
    )
    sys.stderr.flush()
    if clamped >= total:
        sys.stderr.write("\n")
        sys.stderr.flush()


def _slice_transported_photons(
    photons: TransportedPhotonBatch,
    start: int,
    stop: int,
) -> TransportedPhotonBatch:
    """Return one contiguous transported-photon chunk."""

    return TransportedPhotonBatch(
        source_photon_index=photons.source_photon_index[start:stop],
        gun_call_id=photons.gun_call_id[start:stop],
        primary_track_id=photons.primary_track_id[start:stop],
        secondary_track_id=photons.secondary_track_id[start:stop],
        photon_track_id=photons.photon_track_id[start:stop],
        x_mm=photons.x_mm[start:stop],
        y_mm=photons.y_mm[start:stop],
        z_mm=photons.z_mm[start:stop],
        time_ns=photons.time_ns[start:stop],
        wavelength_nm=photons.wavelength_nm[start:stop],
    )


def _concatenate_intensifier_outputs(
    chunks: list[IntensifierOutputBatch],
) -> IntensifierOutputBatch:
    """Concatenate chunked intensifier outputs into one batch."""

    if not chunks:
        return IntensifierOutputBatch.empty()
    return IntensifierOutputBatch(
        source_photon_index=np.concatenate([chunk.source_photon_index for chunk in chunks]),
        gun_call_id=np.concatenate([chunk.gun_call_id for chunk in chunks]),
        primary_track_id=np.concatenate([chunk.primary_track_id for chunk in chunks]),
        secondary_track_id=np.concatenate([chunk.secondary_track_id for chunk in chunks]),
        photon_track_id=np.concatenate([chunk.photon_track_id for chunk in chunks]),
        output_x_mm=np.concatenate([chunk.output_x_mm for chunk in chunks]),
        output_y_mm=np.concatenate([chunk.output_y_mm for chunk in chunks]),
        output_time_ns=np.concatenate([chunk.output_time_ns for chunk in chunks]),
        signal_amplitude_arb=np.concatenate(
            [chunk.signal_amplitude_arb for chunk in chunks]
        ),
        total_gain=np.concatenate([chunk.total_gain for chunk in chunks]),
        wavelength_nm=np.concatenate([chunk.wavelength_nm for chunk in chunks]),
    )


def intensifier_params_from_sim_config(config: SimConfig) -> IntensifierParams:
    """Build the full intensifier parameter bundle from validated `SimConfig`."""

    return IntensifierParams(
        photocathode=photocathode_params_from_sim_config(config),
        mcp=mcp_params_from_sim_config(config),
        phosphor=phosphor_params_from_sim_config(config),
    )


def run_intensifier_pipeline(
    transported_photons: TransportedPhotonBatch,
    params: IntensifierParams,
    rng: np.random.Generator | None = None,
    *,
    show_progress: bool = False,
    chunk_rows: int = _DEFAULT_INTENSIFIER_CHUNK_ROWS,
) -> IntensifierOutputBatch:
    """Run all intensifier stages for one transported-photon batch."""

    if rng is None:
        rng = np.random.default_rng()
    if chunk_rows <= 0:
        raise ValueError("`chunk_rows` must be > 0.")

    logger = get_logger()
    logger.info(f"[intensifier] Input transported photons: {len(transported_photons)}")
    with log_stage("intensifier"):
        total_photons = len(transported_photons)
        output_chunks: list[IntensifierOutputBatch] = []
        photoelectron_count = 0
        mcp_event_count = 0
        for start in range(0, total_photons, chunk_rows):
            stop = min(start + chunk_rows, total_photons)
            chunk = _slice_transported_photons(transported_photons, start, stop)
            photoelectrons = convert_photons_to_photoelectrons(
                chunk,
                params.photocathode,
                rng=rng,
            )
            photoelectron_count += len(photoelectrons)
            mcp_events = convert_photoelectrons_to_mcp_events(
                photoelectrons,
                params.mcp,
                rng=rng,
            )
            mcp_event_count += len(mcp_events)
            output_chunks.append(
                convert_mcp_events_to_intensifier_output(
                    mcp_events,
                    params.phosphor,
                    rng=rng,
                )
            )
            if show_progress:
                _write_compute_progress(stop, total_photons)
        output_events = _concatenate_intensifier_outputs(output_chunks)
        logger.info(f"[intensifier] Photoelectrons: {photoelectron_count}")
        logger.info(f"[intensifier] MCP events: {mcp_event_count}")
    logger.info(f"[intensifier] Output phosphor events: {len(output_events)}")
    return output_events


def run_intensifier_pipeline_from_sim_config(
    config: SimConfig,
    *,
    transport_hdf5_path: str | Path | None = None,
    source_hdf5_path: str | Path | None = None,
    require_in_bounds: bool = True,
    rng: np.random.Generator | None = None,
    show_progress: bool | None = None,
) -> IntensifierOutputBatch:
    """Load HDF5 inputs via `SimConfig` and run the full intensifier pipeline."""

    logger = get_logger()
    logger.info("[intensifier] Loading transported photons.")
    transported_photons = load_transported_photon_batch_from_sim_config(
        config,
        transport_hdf5_path=transport_hdf5_path,
        source_hdf5_path=source_hdf5_path,
        require_in_bounds=require_in_bounds,
        show_progress=config.runner.show_progress,
    )
    params = intensifier_params_from_sim_config(config)
    output_events = run_intensifier_pipeline(
        transported_photons,
        params,
        rng=rng,
        show_progress=(
            bool(config.runner.show_progress)
            if show_progress is None
            else bool(show_progress)
        ),
    )
    intensifier = config.intensifier
    if intensifier is not None and intensifier.write_output_hdf5:
        logger.info("[intensifier] Writing intensifier HDF5 output.")
        write_intensifier_output_hdf5(
            output_events,
            config=config,
            transport_hdf5_path=transport_hdf5_path,
        )
    return output_events
