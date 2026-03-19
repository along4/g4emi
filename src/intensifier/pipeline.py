"""High-level intensifier pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from src.intensifier.io import load_transported_photon_batch_from_sim_config
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
    transport_hdf5_path: str | None = None,
    source_hdf5_path: str | None = None,
    require_in_bounds: bool = True,
    rng: np.random.Generator | None = None,
) -> IntensifierOutputBatch:
    """Load HDF5 inputs via `SimConfig` and run the full intensifier pipeline."""

    transported_photons = load_transported_photon_batch_from_sim_config(
        config,
        transport_hdf5_path=transport_hdf5_path,
        source_hdf5_path=source_hdf5_path,
        require_in_bounds=require_in_bounds,
    )
    params = intensifier_params_from_sim_config(config)
    return run_intensifier_pipeline(
        transported_photons,
        params,
        rng=rng,
    )


@dataclass(slots=True)
class IntensifierPipeline:
    """Small pipeline wrapper for repeated intensifier-stage execution."""

    params: IntensifierParams

    def run(
        self,
        transported_photons: TransportedPhotonBatch,
        rng: np.random.Generator | None = None,
    ) -> IntensifierOutputBatch:
        """Run the configured intensifier pipeline."""

        return run_intensifier_pipeline(
            transported_photons,
            self.params,
            rng=rng,
        )

    @classmethod
    def from_sim_config(cls, config: SimConfig) -> IntensifierPipeline:
        """Construct a pipeline from validated `SimConfig`."""

        return cls(params=intensifier_params_from_sim_config(config))
