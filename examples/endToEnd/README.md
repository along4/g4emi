# End-to-End Example

This example runs the full pipeline from one command:

1. Load/validate SimConfig YAML
2. Generate Geant4 macro
3. Run `g4emi`
4. Transport photons to intensifier plane
5. Run the intensifier pipeline
6. Run the Timepix sensor pipeline and write `timepix_hits_<subrun>.h5`

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
optical:
  showTransportProgress: true

runner:
  binary: g4emi
  showProgress: true
  verifyOutput: true
```

If the YAML enables `intensifier.write_output_hdf5`, the example also writes:

- `<run_root>/sensor/intensifier_output_events_<subrun>.h5`

The Timepix sensor stage always writes:

- `<run_root>/sensor/timepix_hits_<subrun>.h5`
