"""High-level intensifier pipeline orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from src.intensifier.io import intensifier_output_hdf5_path_from_sim_config
from src.intensifier.io import load_transported_photon_batch_from_sim_config
from src.intensifier.io import resolve_intensifier_input_hdf5_paths
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
) -> IntensifierOutputBatch:
    """Run all intensifier stages for one transported-photon batch."""

    if rng is None:
        rng = np.random.default_rng()

    photoelectrons = convert_photons_to_photoelectrons(
        transported_photons,
        params.photocathode,
        rng=rng,
    )
    mcp_events = convert_photoelectrons_to_mcp_events(
        photoelectrons,
        params.mcp,
        rng=rng,
    )
    return convert_mcp_events_to_intensifier_output(
        mcp_events,
        params.phosphor,
        rng=rng,
    )


def run_intensifier_pipeline_from_sim_config(
    config: SimConfig,
    *,
    transport_hdf5_path: str | Path | None = None,
    source_hdf5_path: str | Path | None = None,
    require_in_bounds: bool = True,
    rng: np.random.Generator | None = None,
) -> IntensifierOutputBatch:
    """Load HDF5 inputs via `SimConfig` and run the full intensifier pipeline."""

    transport_path_for_write = (
        Path(transport_hdf5_path).resolve()
        if transport_hdf5_path is not None
        else None
    )
    transported_photons = load_transported_photon_batch_from_sim_config(
        config,
        transport_hdf5_path=transport_hdf5_path,
        source_hdf5_path=source_hdf5_path,
        require_in_bounds=require_in_bounds,
    )
    params = intensifier_params_from_sim_config(config)
    output_events = run_intensifier_pipeline(
        transported_photons,
        params,
        rng=rng,
    )
    intensifier = config.intensifier
    if intensifier is not None and intensifier.write_output_hdf5:
        if transport_path_for_write is None:
            transport_path_for_write = resolve_intensifier_input_hdf5_paths(
                config,
                transport_hdf5_path=transport_hdf5_path,
                source_hdf5_path=source_hdf5_path,
            )[0]
        write_intensifier_output_hdf5(
            output_events,
            config=config,
            transport_hdf5_path=transport_path_for_write,
            output_hdf5_path=intensifier_output_hdf5_path_from_sim_config(config),
        )
    return output_events
