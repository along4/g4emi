# Lightweight Analysis Examples

This folder contains lightweight HDF5 analysis examples for generated
simulation outputs.

Entry points:
- `hdf5_lite_analyzer_example.py`: spatial quick-look plots
- `hdf5_timing_analyzer_example.py`: photon creation delay histogram and fit
- `hdf5_secondary_track_length_analyzer_example.py`: secondary track-length overlay
- `hdf5_event_recoil_analyzer_example.py`: event-level neutron hit, recoil-path, and photon-origin view

Run from repo root:

```bash
pixi run python examples/analysisLite/hdf5_lite_analyzer_example.py \
  data/CanonEF50mmf1p0L_run/simulatedPhotons/photon_optical_interface_hits_0000.h5
```

To force photon-origin and photon-exit plots to a fixed width/height in mm:

```bash
pixi run python examples/analysisLite/hdf5_lite_analyzer_example.py \
  data/CanonEF50mmf1p0L_run/simulatedPhotons/photon_optical_interface_hits_0000.h5 \
  --sim-config-yaml examples/yamlFiles/CanonEF50mmf1p0L_example.yaml \
  --xy-dimensions 50 50
```

Module-level analysis docs live in
[`analysis/README.md`](../../analysis/README.md).

The event-level example automatically uses the sibling `transportedPhotons`
HDF5 file when present so photon origins can be split by whether they reached
the intensifier.
