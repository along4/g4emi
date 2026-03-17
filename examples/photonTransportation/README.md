# Photon Transportation Examples

This folder contains the SimConfig-driven optical transport example.

Current entry point:
- `optical_transport_example.py`: reads simulation HDF5 output, transports
  `/photons` hits through the configured primary lens, and writes a
  `transportedPhotons` HDF5 file.

Run from repo root:

```bash
pixi run python examples/photonTransportation/optical_transport_example.py \
  examples/yamlFiles/CanonEF50mmf1p0L_example.yaml
```
