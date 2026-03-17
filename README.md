# g4emi

`g4emi` is a Geant4-based simulation for scintillator and neutron-GPS workflows
with optical-photon recording at an optical-interface plane.

This repository also includes a Python configuration layer for YAML-driven run
setup, optical transport helpers, and lightweight analysis examples.

## Quick Start

The recommended setup path is `pixi`.

```bash
pixi install
pixi run build-sim
```

Run a macro-driven simulation:

```bash
pixi run run-neutron-gps
```

Run a YAML-driven example:

```bash
pixi run python examples/SimulationSetup/CanonEF50mmf1p0L_example.py
pixi run g4emi data/CanonEF50mmf1p0L_run/macros/CanonEF50mmf1p0L_run.mac
```

## Core Workflows

- Run Geant4 directly from a macro: `pixi run run-neutron-gps`
- Generate and run from YAML: `pixi run python examples/runSimulation/run_simulation_from_yaml.py examples/yamlFiles/CanonEF50mmf1p0L_example.yaml`
- Transport optical-interface hits to the intensifier plane: `pixi run python examples/photonTransportation/optical_transport_example.py examples/yamlFiles/CanonEF50mmf1p0L_example.yaml`
- Generate lightweight analysis outputs: `pixi run python examples/analysisLite/hdf5_lite_analyzer_example.py data/CanonEF50mmf1p0L_run/simulatedPhotons/photon_optical_interface_hits.h5`

For the full YAML -> simulation -> transport pipeline, see
[examples/endToEnd/README.md](examples/endToEnd/README.md).

For analysis examples and module-level guidance, see
[analysis/README.md](analysis/README.md).

## Repository Layout

- `sim/`: Geant4 application code, headers, and macro files
- `src/config/`: YAML models, validation, and macro-generation utilities
- `src/optics/`: optical transport and lens tooling
- `examples/`: runnable workflow examples
- `analysis/`: lightweight analysis helpers for generated HDF5 outputs
- `test/`: unit tests and test documentation

## Further Documentation

- Examples index: [examples/README.md](examples/README.md)
- Analysis helpers: [analysis/README.md](analysis/README.md)
- HDF5 schema reference: [docs/hdf5_schema.md](docs/hdf5_schema.md)
- End-to-end workflow: [examples/endToEnd/README.md](examples/endToEnd/README.md)
- Tests: [test/README.md](test/README.md)
- Lens catalog notes: [lenses/README.md](lenses/README.md)
- Scintillator catalog notes: [scintillators/README.md](scintillators/README.md)
