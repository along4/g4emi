# HDF5 Schema

This document describes the current `g4emi` HDF5 output structure.

It covers:

- simulation output written by `g4emi`
- optical transport output written by `src/optics/OpticalTransport.py`

This is a reference for the current writer schema. It does not describe legacy
aliases or older ad hoc outputs.

## Output Layout

Simulation output is written under the `simulatedPhotons/` stage.

Typical paths:

- `<run_root>/simulatedPhotons/photon_optical_interface_hits.h5`
- `<run_root>/simulatedPhotons/photon_optical_interface_hits_<subrun>.h5`

Optical transport output is written under the `transportedPhotons/` stage.

Typical paths:

- `<run_root>/transportedPhotons/photons_intensifier_hits.h5`
- `<run_root>/transportedPhotons/photons_intensifier_hits_<subrun>.h5`

## Simulation Datasets

Simulation HDF5 files contain these datasets:

- `/primaries`
- `/secondaries`
- `/photons`

Selection semantics:

- `/primaries` contains primaries that created at least one secondary in the
  scintillator volume.
- `/secondaries` contains secondaries linked to at least one detected
  optical-interface photon hit.
- `/photons` contains one row per detected optical-interface photon hit.

### `/primaries`

Fields:

- `gun_call_id`
- `primary_track_id`
- `primary_species`
- `primary_x_mm`
- `primary_y_mm`
- `primary_energy_MeV`
- `primary_interaction_time_ns`
- `primary_created_secondary_count`
- `primary_generated_optical_photon_count`
- `primary_detected_optical_interface_photon_count`

Notes:

- `gun_call_id` is the Geant4 event ID.
- `primary_track_id` is the event-local Geant4 track ID of the primary.
- `primary_interaction_time_ns` is the first recorded scintillator interaction
  time for the primary and is written as `NaN` when no such interaction time
  was recorded.
- The three `*_count` fields summarize activity attributed to the primary
  ancestry inside the scintillator.

### `/secondaries`

Fields:

- `gun_call_id`
- `primary_track_id`
- `secondary_track_id`
- `secondary_species`
- `secondary_origin_x_mm`
- `secondary_origin_y_mm`
- `secondary_origin_z_mm`
- `secondary_origin_energy_MeV`
- `secondary_end_x_mm`
- `secondary_end_y_mm`
- `secondary_end_z_mm`

Notes:

- `secondary_track_id` is the event-local Geant4 track ID of the secondary.
- `secondary_end_*_mm` is written as `NaN` when no usable end position was
  recorded for that secondary.

### `/photons`

Fields:

- `gun_call_id`
- `primary_track_id`
- `secondary_track_id`
- `photon_track_id`
- `photon_creation_time_ns`
- `photon_origin_x_mm`
- `photon_origin_y_mm`
- `photon_origin_z_mm`
- `photon_scint_exit_x_mm`
- `photon_scint_exit_y_mm`
- `photon_scint_exit_z_mm`
- `optical_interface_hit_x_mm`
- `optical_interface_hit_y_mm`
- `optical_interface_hit_time_ns`
- `optical_interface_hit_dir_x`
- `optical_interface_hit_dir_y`
- `optical_interface_hit_dir_z`
- `optical_interface_hit_pol_x`
- `optical_interface_hit_pol_y`
- `optical_interface_hit_pol_z`
- `optical_interface_hit_energy_eV`
- `optical_interface_hit_wavelength_nm`

Notes:

- `/photons` stores one row per detected optical-interface crossing.
- `photon_creation_time_ns` and `optical_interface_hit_time_ns` share the same
  Geant4 event-local global-time basis.
- `photon_scint_exit_*_mm` is written as `NaN` when no scintillator-exit
  crossing was recorded for that photon.
- The `optical_interface_hit_*` fields capture position, time, direction,
  polarization, energy, and wavelength at the optical-interface crossing.

## Optical Transport Dataset

Transport HDF5 files contain:

- copied `/primaries`
- copied `/secondaries`
- `/transported_photons`

### `/transported_photons`

Fields:

- `source_photon_index`
- `gun_call_id`
- `primary_track_id`
- `secondary_track_id`
- `photon_track_id`
- `intensifier_hit_x_mm`
- `intensifier_hit_y_mm`
- `intensifier_hit_z_mm`
- `reached_intensifier`
- `in_bounds`

Notes:

- `source_photon_index` is the row index in the source `/photons` dataset used
  for transport.
- `intensifier_hit_*_mm` is written as `NaN` when the photon misses the lens or
  sensor in transport.
- `reached_intensifier` is `True` when transport produced a finite hit on the
  intensifier plane.
- `in_bounds` is `True` when the hit falls inside the configured intensifier
  input screen. If no input screen is defined, reached hits are treated as
  in-bounds by definition.

## Transport File Attributes

Transport HDF5 files also write root-level attributes describing provenance and
transport assumptions.

Common attributes:

- `source_hdf5`
- `run_id`
- `lens_name`
- `lens_zmx_path`
- `object_plane`
- `optical_interface_represents`
- `transport_engine`
- `transport_chunk_rows`
- `transport_chunk_target_mib`
- `generated_utc`

Optional attributes:

- `lens_smx_path`
- `intensifier_model`
- `intensifier_input_screen_defined`
- `intensifier_input_screen_diameter_mm`
- `intensifier_input_screen_center_mm`
- `intensifier_input_screen_magnification`
- `intensifier_input_screen_coordinate_frame`

Notes:

- `intensifier_input_screen_defined` is `False` when no input screen geometry
  is configured.
- When an input screen is configured, the related diameter, center,
  magnification, and coordinate-frame attributes are also written.

## Schema Sources

The current writer schema is defined in:

- `sim/include/structures.hh`
- `sim/src/SimIO.cc`
- `src/optics/OpticalTransport.py`
- `src/common/hdf5_schema.py`
