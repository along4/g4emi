# Simulation Setup Examples

This folder contains YAML-driven macro-generation examples.

Current entry point:
- `CanonEF50mmf1p0L_example.py`: writes a standard batch macro and a
  mask-visualization macro for the Canon example setup.

Run from repo root:

```bash
pixi run python examples/SimulationSetup/CanonEF50mmf1p0L_example.py
```

The script uses the shared YAML in
[`examples/yamlFiles/CanonEF50mmf1p0L_example.yaml`](../yamlFiles/CanonEF50mmf1p0L_example.yaml)
and prints the generated macro paths and follow-up commands.
