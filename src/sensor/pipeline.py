"""High-level Timepix sensor pipeline orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src.common.logger import get_logger
from src.common.logger import log_stage
from src.intensifier.models import IntensifierOutputBatch
from src.intensifier.pipeline import run_intensifier_pipeline_from_sim_config
from src.sensor.io import write_timepix_hits_hdf5
from src.sensor.models import TimepixHitBatch
from src.sensor.models import TimepixParams
from src.sensor.timepix import convert_timepix_events_to_hits
from src.sensor.timepix import map_intensifier_output_to_timepix_events
from src.sensor.timepix import timepix_params_from_sim_config

if TYPE_CHECKING:
    from src.config.SimConfig import SimConfig


def run_timepix_pipeline(
    intensifier_output: IntensifierOutputBatch,
    params: TimepixParams,
) -> TimepixHitBatch:
    """Map intensifier output onto the Timepix area and apply readout behavior."""

    logger = get_logger()
    logger.info(f"[sensor] Input intensifier events: {len(intensifier_output)}")
    with log_stage("sensor"):
        mapped_events = map_intensifier_output_to_timepix_events(intensifier_output, params)
        logger.info(f"[sensor] In-bounds mapped Timepix events: {len(mapped_events)}")
        hits = convert_timepix_events_to_hits(mapped_events, params)
    logger.info(f"[sensor] Output Timepix hits: {len(hits)}")
    return hits


def run_timepix_pipeline_from_sim_config(
    config: SimConfig,
    *,
    transport_hdf5_path: str | Path | None = None,
    source_hdf5_path: str | Path | None = None,
    output_hdf5_path: str | Path | None = None,
    require_in_bounds: bool = True,
) -> TimepixHitBatch:
    """Run intensifier and Timepix stages from `SimConfig` and write HDF5 output."""

    logger = get_logger()
    intensifier_output = run_intensifier_pipeline_from_sim_config(
        config,
        transport_hdf5_path=transport_hdf5_path,
        source_hdf5_path=source_hdf5_path,
        require_in_bounds=require_in_bounds,
    )
    params = timepix_params_from_sim_config(config)
    hits = run_timepix_pipeline(intensifier_output, params)
    logger.info("[sensor] Writing Timepix HDF5 output.")
    write_timepix_hits_hdf5(
        hits,
        config=config,
        transport_hdf5_path=transport_hdf5_path,
        source_hdf5_path=source_hdf5_path,
        output_hdf5_path=output_hdf5_path,
    )
    return hits
