# Analysis Helpers

This directory contains lightweight analysis helpers for `g4emi` HDF5 outputs.

These modules are intended for quick inspection, plotting, and small analysis
tasks. They are not meant to be a full analysis framework.

For runnable scripts, see
[`examples/analysisLite/README.md`](../examples/analysisLite/README.md).

## Module Layout

- `analysis/spatial.py`: neutron, photon, optical-interface, and intensifier
  spatial quick-look plots
- `analysis/timing.py`: photon creation delay extraction, histograms, and
  bounded three-component fits
- `analysis/secondaries.py`: secondary track-length grouping and overlays
- `analysis/events.py`: event-level recoil-path visualization
- `analysis/io.py`: shared HDF5 reads, field validation, and small dataset helpers
- `analysis/plotting.py`: shared matplotlib helpers used by the analysis modules

The user-facing entry points live in the domain modules. `io.py` and
`plotting.py` are support code.

## Scope

These helpers are useful for:

- quick sanity checks on generated HDF5 output
- lightweight exploratory plotting
- starter code for custom downstream analysis

These helpers are not intended to:

- preserve legacy ad hoc schema aliases
- replace a project-specific analysis pipeline
- serve as a general-purpose plotting framework

## Key Entry Points

Spatial:
- `neutron_hits_to_image(...)`
- `photon_origins_to_image(...)`
- `photon_exit_to_image(...)`
- `optical_interface_photons_to_image(...)`
- `intensifier_photons_to_image(...)`
- `timepix_tot_to_image(...)`

Timing:
- `photon_creation_delays_ns(...)`
- `photon_creation_delay_to_histogram(...)`
- `fit_photon_creation_delay_histogram(...)`

Secondaries:
- `secondary_track_lengths_by_species_mm(...)`
- `secondary_track_lengths_overlay_to_histogram(...)`

Events:
- `event_recoil_paths_to_image(...)`

## Behavior Notes

- The analysis modules target the current writer schema used by the simulation
  and optical transport code.
- `photon_creation_delay_to_histogram(...)` computes
  `photon_creation_time_ns - primary_interaction_time_ns` by matching
  `/photons` rows to `/primaries` on `(gun_call_id, primary_track_id)`.
- `fit_photon_creation_delay_histogram(...)` is an exploratory bounded
  three-component fit, not a full inference workflow.
- `photon_origins_to_image(...)` and `photon_exit_to_image(...)` can use
  explicit XY limits, derive XY extent from SimConfig YAML, or infer bounds
  from HDF5 data.
- `intensifier_photons_to_image(...)` uses intensifier screen metadata from
  transport HDF5 attributes when available.
- `timepix_tot_to_image(...)` plots Timepix pixel hits over the observed pixel
  extent and weights each pixel by summed `time_over_threshold_ns`.

## Tests

Analysis unit tests live under `test/unit/analysis/`.

Run them from repo root:

```bash
python -m unittest discover -s test/unit/analysis -p "test_*.py"
```

If using pixi, `pixi run test-python` includes them.
