# Lens Asset Catalog

This directory stores all optical-lens assets used by g4emi.

Layout:
- `catalog.yaml`: index of available lens entries and default selection
- `zmxFiles/`: Zemax sequential lens prescriptions (`.zmx`)
- `smxFiles/`: optional glass-replacement sidecars (`.smx`) used by rayoptics

Conventions:
- Lens IDs in `catalog.yaml` should map to one `.zmx` file and, when needed,
  one `.smx` file with the same base name.
- `SimConfig` supports `optical.lenses[*].catalogId` to hydrate `name`,
  `zmxFile`, and `smxFile` from this catalog.
