# Example YAML Files

This folder contains shared example `SimConfig` YAML inputs used by the scripts
under `examples/`.

Current files:
- `CanonEF50mmf1p0L_example.yaml`: primary end-to-end example configuration
- `EJ200.yaml`: catalog-driven scintillator example with overrides
- `EJ276D.yaml`: explicit three-component timing example for scintillator config
- `three_component_timing_example.yaml`: timing-focused example configuration

These YAMLs are consumed by scripts in:
- [`SimulationSetup/`](../SimulationSetup/README.md)
- [`runSimulation/`](../runSimulation/README.md)
- [`photonTransportation/`](../photonTransportation/README.md)
- [`endToEnd/`](../endToEnd/README.md)
- [`scintillatorCataloging/`](../scintillatorCataloging/README.md)
