# Lightweight HDF5 Analyzer

This repository is primarily simulation-focused. The core scope is generating
Geant4 outputs (HDF5), not providing a full analysis framework.

Users are expected to build their own analysis pipelines for their specific
science and workflow needs.

To make onboarding easier, this folder includes a lightweight demonstration
module: `hdf5Analyzer.py`.

## Why this exists

- show how to read the project HDF5 schema with `h5py`
- provide quick visual sanity checks with minimal dependencies
- serve as starter code that users can copy/extend in their own projects

## What it provides

- `neutron_hits_to_image(...)`
- `photon_origins_to_image(...)`
- `photon_exit_to_image(...)`
- `optical_interface_photons_to_image(...)`
- `intensifier_photons_to_image(...)`
- `photon_creation_delay_to_histogram(...)`

These functions create 2D histogram images (`x` vs `y`) from the relevant
HDF5 datasets, plus a 1D timing histogram for photon creation delay.

`photon_creation_delay_to_histogram(...)` computes:

- `photon_creation_time_ns - primary_interaction_time_ns`

It reads `/primaries` and `/photons`, matches rows by
`(gun_call_id, primary_track_id)`, and skips rows where the primary
interaction time is missing (`NaN`).

`fit_photon_creation_delay_histogram(...)` performs a bounded 3-component
exponential fit against histogram bin counts and returns fitted decay
constants and yield fractions. This is intended as a lightweight exploratory
tool, not a full statistical inference pipeline.

The analyzer targets the current writer schema defined by:
- `sim/include/structures.hh`
- `sim/src/SimIO.cc`
- `src/optics/OpticalTransport.py`

It is not intended to preserve legacy field aliases from older ad hoc outputs.

By default, `neutron_hits_to_image`, `photon_origins_to_image`, and
`photon_exit_to_image` use a shared XY range so their image scale is directly
comparable.

`intensifier_photons_to_image(...)` uses the intensifier input-screen metadata
from transport HDF5 attributes (when present) to fix plot extent to the
physical image-circle footprint and can overlay the circle boundary.

`photon_origins_to_image(...)` and `photon_exit_to_image(...)` support three
range modes (highest precedence first):
- explicit user limits (`xy_range_override` / `--xy-limits`)
- scintillator XY extent from SimConfig YAML
- inferred bounds from HDF5 data (default fallback)

## Example usage

Quick-look spatial example:
- `examples/analysisLite/hdf5_lite_analyzer_example.py`

Timing-focused example:
- `examples/analysisLite/hdf5_timing_analyzer_example.py`

Run from repo root:

```bash
pixi run python examples/analysisLite/hdf5_lite_analyzer_example.py \
  data/CanonEF50mmf1p0L_run/simulatedPhotons/photon_optical_interface_hits.h5
```

The lite analyzer script uses an existing simulation output HDF5 file and writes PNGs to
`<run_root>/plots/` by default (for example:
`data/CanonEF50mmf1p0L_run/plots/`).

If a sibling transport file exists at:

`data/<run>/transportedPhotons/photons_intensifier_hits.h5`

the script also writes `photons_intensifier_hits.png`.
You can also pass an explicit transport file via:

`--transport-hdf5-path <path/to/photons_intensifier_hits.h5>`

Run the timing-only example from repo root:

```bash
pixi run python examples/analysisLite/hdf5_timing_analyzer_example.py \
  data/CanonEF50mmf1p0L_run/simulatedPhotons/photon_optical_interface_hits.h5
```

This writes `photon_creation_delay.png` to the same default output directory.

To overlay the configured decay model and fit the histogram:

```bash
pixi run python examples/analysisLite/hdf5_timing_analyzer_example.py \
  data/CanonEF50mmf1p0L_run/simulatedPhotons/photon_optical_interface_hits.h5 \
  --fit \
  --sim-config-yaml examples/yamlFiles/CanonEF50mmf1p0L_example.yaml
```

When `--sim-config-yaml` is provided, the script loads the active 3-component
profile selected for the configured source particle, overlays that model on
the histogram, and uses it as the initial guess for fitting.
