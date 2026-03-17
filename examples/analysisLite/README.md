# Lightweight Analysis Examples

This folder contains lightweight HDF5 analysis examples for generated
simulation outputs.

Entry points:
- `hdf5_lite_analyzer_example.py`: spatial quick-look plots
- `hdf5_timing_analyzer_example.py`: photon creation delay histogram and fit
- `hdf5_secondary_track_length_analyzer_example.py`: secondary track-length overlay
- `hdf5_event_recoil_analyzer_example.py`: event-level recoil-path view

Run from repo root:

```bash
pixi run python examples/analysisLite/hdf5_lite_analyzer_example.py \
  data/CanonEF50mmf1p0L_run/simulatedPhotons/photon_optical_interface_hits.h5
```

Module-level analysis docs live in
[`analysis/README.md`](../../analysis/README.md).
