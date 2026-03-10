# End-to-End Example

This example runs the full pipeline from one command:

1. Load/validate SimConfig YAML
2. Generate Geant4 macro
3. Run `g4emi`
4. Transport photons to intensifier plane

Run from repo root:

```bash
pixi run python examples/endToEnd/end_to_end_example.py \
  examples/yamlFiles/CanonEF50mmf1p0L_example.yaml
```

Optional flags:

- `--beam-on <N>`: override `simulation.numberOfParticles`
- `--dry-run`: print paths/commands only
- `--g4emi-binary <path-or-name>`: override `runner.binary` for this invocation
- `--no-overwrite-transport`: fail if transport HDF5 already exists

The example YAML files now include a top-level `runner` block:

```yaml
runner:
  binary: g4emi
  verifyOutput: true
```
