# Lightweight HDF5 Analyzer

This repository is primarily simulation-focused. The core scope is generating
Geant4 outputs (HDF5), not providing a full analysis framework.

Users are expected to build their own analysis pipelines for their specific
science and workflow needs.

To make onboarding easier, this folder includes a lightweight demonstration
module: `hfdf5Analyzer.py`.

## Why this exists

- show how to read the project HDF5 schema with `h5py`
- provide quick visual sanity checks with minimal dependencies
- serve as starter code that users can copy/extend in their own projects

## What it provides

- `neutron_hits_to_image(...)`
- `photon_origins_to_image(...)`
- `photon_exit_to_image(...)`
- `optical_interface_photons_to_image(...)`

These functions create 2D histogram images (`x` vs `y`) from the relevant
HDF5 datasets.

By default, `neutron_hits_to_image`, `photon_origins_to_image`, and
`photon_exit_to_image` use a shared XY range so their image scale is directly
comparable.

## Example usage

See:
- `examples/analysisLite/hdf5_lite_analyzer_example.py`

Run from repo root:

```bash
pixi run python examples/analysisLite/hdf5_lite_analyzer_example.py \
  data/CanonEF50mmf1p0L_run/simulatedPhotons/photon_optical_interface_hits.h5
```

The script uses an existing simulation output HDF5 file and writes PNGs to
`analysis/outputs/`.
