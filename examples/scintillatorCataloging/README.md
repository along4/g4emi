# Scintillator Cataloging Examples

This folder contains examples that start from the local scintillator catalog
and apply targeted overrides through YAML.

Contents:
- `scintillator_catalog.py`: generate a runnable macro from a catalog-backed YAML
- `EJ276D_example.mac`: example generated macro artifact

Run from repo root:

```bash
pixi run python examples/scintillatorCataloging/scintillator_catalog.py
```

The default YAML inputs for this flow live in
[`examples/yamlFiles/README.md`](../yamlFiles/README.md).
