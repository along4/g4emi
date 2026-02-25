# Scintillator Catalog

This directory stores a Python-native scintillator catalog for `g4emi`.

Current materials:
- `EJ200` (default baseline)
- `EJ-426` (SSLG4-derived ZnS:Ag/LiF-6 style entry; Li-6 enrichment noted)
- `EJ-276D` (SSLG4-derived optical curves/constants)
- `EJ-276G` (SSLG4-derived optical curves/constants)

## Layout

- `catalog.yaml`: catalog index (version, default material, material registry).
- `materials/*.yaml`: per-scintillator metadata, composition, and curve references.
- `curves/<material>/*.csv`: optical property curves (`energy_eV,value`).

## Curve file format

- UTF-8 text.
- Header row: `energy_eV,value` (recommended).
- Data rows: two numeric columns.
- Comments are allowed with `#`.

Example:

```csv
energy_eV,value
2.00,1.58
2.40,1.58
```
