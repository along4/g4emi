"""Lightweight HDF5 plotting utilities for g4emi outputs."""

from __future__ import annotations

from analysis.events import event_recoil_paths_to_image
from analysis.secondaries import (
    secondary_track_lengths_by_species_mm,
    secondary_track_lengths_overlay_to_histogram,
)
from analysis.spatial import (
    intensifier_photons_to_image,
    neutron_hits_to_image,
    optical_interface_photons_to_image,
    photon_exit_to_image,
    photon_origins_to_image,
)
from analysis.timing import (
    PhotonCreationDelayFitResult,
    ScintillationDecayComponent,
    decay_model_bin_counts,
    fit_photon_creation_delay_histogram,
    photon_creation_delay_to_histogram,
    photon_creation_delays_ns,
)


__all__ = [
    "ScintillationDecayComponent",
    "PhotonCreationDelayFitResult",
    "decay_model_bin_counts",
    "fit_photon_creation_delay_histogram",
    "photon_creation_delays_ns",
    "secondary_track_lengths_by_species_mm",
    "neutron_hits_to_image",
    "photon_origins_to_image",
    "photon_exit_to_image",
    "optical_interface_photons_to_image",
    "intensifier_photons_to_image",
    "photon_creation_delay_to_histogram",
    "secondary_track_lengths_overlay_to_histogram",
    "event_recoil_paths_to_image",
]
