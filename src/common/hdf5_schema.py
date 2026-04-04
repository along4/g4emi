"""Canonical HDF5 dataset and field names for g4emi outputs.

This module is the Python-side schema reference for analysis consumers.

- `/primaries`, `/secondaries`, and `/photons` are written by the simulation
  writer in `sim/include/structures.hh` and `sim/src/SimIO.cc`.
- `/transported_photons` is written by the optical transport pipeline in
  `src/optics/OpticalTransport.py`.

These constants intentionally describe the current writer schema only.
Legacy field aliases do not belong here.
"""

from __future__ import annotations

DATASET_PRIMARIES = "primaries"
DATASET_SECONDARIES = "secondaries"
DATASET_PHOTONS = "photons"
DATASET_TRANSPORTED_PHOTONS = "transported_photons"
DATASET_INTENSIFIER_OUTPUT_EVENTS = "intensifier_output_events"
DATASET_TIMEPIX_HITS = "timepix_hits"

PRIMARY_FIELDS = (
    "gun_call_id",
    "primary_track_id",
    "primary_species",
    "primary_x_mm",
    "primary_y_mm",
    "primary_energy_MeV",
    "primary_interaction_time_ns",
    "primary_created_secondary_count",
    "primary_generated_optical_photon_count",
    "primary_detected_optical_interface_photon_count",
)

SECONDARY_FIELDS = (
    "gun_call_id",
    "primary_track_id",
    "secondary_track_id",
    "secondary_species",
    "secondary_origin_x_mm",
    "secondary_origin_y_mm",
    "secondary_origin_z_mm",
    "secondary_origin_energy_MeV",
    "secondary_end_x_mm",
    "secondary_end_y_mm",
    "secondary_end_z_mm",
)

PHOTON_FIELDS = (
    "gun_call_id",
    "primary_track_id",
    "secondary_track_id",
    "photon_track_id",
    "photon_creation_time_ns",
    "photon_origin_x_mm",
    "photon_origin_y_mm",
    "photon_origin_z_mm",
    "photon_scint_exit_x_mm",
    "photon_scint_exit_y_mm",
    "photon_scint_exit_z_mm",
    "optical_interface_hit_x_mm",
    "optical_interface_hit_y_mm",
    "optical_interface_hit_time_ns",
    "optical_interface_hit_dir_x",
    "optical_interface_hit_dir_y",
    "optical_interface_hit_dir_z",
    "optical_interface_hit_pol_x",
    "optical_interface_hit_pol_y",
    "optical_interface_hit_pol_z",
    "optical_interface_hit_energy_eV",
    "optical_interface_hit_wavelength_nm",
)

TRANSPORTED_PHOTON_FIELDS = (
    "source_photon_index",
    "gun_call_id",
    "primary_track_id",
    "secondary_track_id",
    "photon_track_id",
    "intensifier_hit_x_mm",
    "intensifier_hit_y_mm",
    "intensifier_hit_z_mm",
    "reached_intensifier",
    "in_bounds",
)

INTENSIFIER_OUTPUT_FIELDS = (
    "source_photon_index",
    "gun_call_id",
    "primary_track_id",
    "secondary_track_id",
    "photon_track_id",
    "output_x_mm",
    "output_y_mm",
    "output_time_ns",
    "signal_amplitude_arb",
    "total_gain",
    "wavelength_nm",
)

TIMEPIX_HIT_FIELDS = (
    "gun_call_id",
    "primary_track_id",
    "secondary_track_id",
    "x_pixel",
    "y_pixel",
    "time_of_arrival_ns",
    "time_over_threshold_ns",
    "contribution_count",
)

PRIMARY_INTERACTION_TIME_FIELD = "primary_interaction_time_ns"
PHOTON_SCINT_EXIT_X_FIELD = "photon_scint_exit_x_mm"
PHOTON_SCINT_EXIT_Y_FIELD = "photon_scint_exit_y_mm"
PHOTON_SCINT_EXIT_Z_FIELD = "photon_scint_exit_z_mm"
SECONDARY_END_X_FIELD = "secondary_end_x_mm"
SECONDARY_END_Y_FIELD = "secondary_end_y_mm"
SECONDARY_END_Z_FIELD = "secondary_end_z_mm"
