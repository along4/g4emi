# Run Simulation Examples

This folder contains scripts that generate macros from YAML and launch `g4emi`.

Entry points:
- `run_simulation_from_yaml.py`: one YAML -> one macro -> one run
- `run_simulation_in_batch_mode.py`: one YAML -> sequential sub-runs with
  per-sub-run macro generation

Run from repo root:

```bash
pixi run python examples/runSimulation/run_simulation_from_yaml.py \
  examples/yamlFiles/CanonEF50mmf1p0L_example.yaml
```

For the full pipeline including optical transport, see
[`examples/endToEnd/README.md`](../endToEnd/README.md).
