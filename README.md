# g4emi: Scintillator + Neutron GPS (Geant4)

This repository contains:

- A Geant4 simulation (`g4emi`) for neutron-driven scintillation with optical photon recording at an optical-interface plane.
- A Python configuration layer for geometry, macro generation, and optics workflows.

## 1. Getting Started

### 1.1 Installation with pixi

The `pixi.toml` in this repository installs Python, Geant4, and build tooling from `conda-forge`.
Supported platforms in the project manifest are `linux-64` and `osx-arm64`.

```bash
pixi install
pixi run check-geant4
pixi run check-ray-optics
pixi run build-sim
```

After build, the `g4emi` binary is available through Pixi tasks:

```bash
pixi run run-neutron-gps
pixi run run-vis
```

### 1.2 Installation of just g4emi

If you only want the C++ simulation (no Pixi/Python workflow), install these system dependencies:

- Geant4 (`>=11.2`) with UI and visualization components
- HDF5 with C and HL components
- CMake (`>=3.16`)
- A C++17 compiler

Then configure and build:

```bash
# Example if your Geant4 install provides this setup script
source /opt/geant4/geant4-v11.2.1/install/bin/geant4.sh

cmake -S . -B build
cmake --build build -j
```

Run the simulation directly:

```bash
./build/g4emi sim/macros/neutron_gps.mac
```

## 2. Example Usage

### 2.1 Batch neutron GPS run

```bash
pixi run run-neutron-gps
```

### 2.2 Interactive run with visualization

```bash
pixi run run-vis
```

### 2.3 YAML-driven macro generation from Python

Generate a macro from `examples/CanonEF50mmf1p0L_example.yaml`:

```bash
pixi run python examples/CanonEF50mmf1p0L_example.py
```

The script prints the generated macro path and a run command. By default (with the current example YAML), the macro is written under:

```text
data/CanonEF50mmf1p0L_run/macros/CanonEF50mmf1p0L_run.mac
```

Run it with:

```bash
pixi run g4emi data/CanonEF50mmf1p0L_run/macros/CanonEF50mmf1p0L_run.mac
```

### 2.4 Catalog-based scintillator override example

`examples/scintillatorCataloging/EJ200.yaml` demonstrates:
- `scintillator.catalogId: EJ200` baseline hydration from the local catalog.
- targeted manual overrides in `scintillator.properties` (e.g. `absLength`, `timeComponents`, `scintYield`).
- `examples/scintillatorCataloging/EJ276D.yaml`
  demonstrates explicit 3-entry `timeComponents` schema usage.

For an actual run, use the Python generator first so output subdirectories
(`data/<SimulationRunID>/simulatedPhotons`) are created before Geant4 writes:

```bash
pixi run python examples/scintillatorCataloging/scintillator_catalog.py
```

Then run the macro path printed by the script (default location):

```bash
pixi run g4emi data/ScintCatalog_example/macros/ScintCatalog_example.mac
```

### 2.5 Lightweight HDF5 analyzer example

This repo is simulation-first. Users are encouraged to implement analysis code
tailored to their own workflows.

A lightweight demonstration analyzer is provided in:

```text
analysis/hfdf5Analyzer.py
```

Design notes and intent are documented in:

```text
analysis/README.md
```

A runnable example is available in:

```bash
pixi run python examples/analysisLite/hdf5_lite_analyzer_example.py \
  data/CanonEF50mmf1p0L_run/simulatedPhotons/photon_optical_interface_hits.h5
```

## 3. Simulation Output Structures

### 3.1 Output directory structure

Runtime output files are staged under an effective output root (`output_path`, or fallback `data/`).

- Without runname:
  - `<output_root>/simulatedPhotons/photon_optical_interface_hits.h5`
- With runname:
  - `<output_root>/<runname>/simulatedPhotons/photon_optical_interface_hits.h5`

Python-side helpers also use these sibling stage folders:

- `<output_root>/<runname>/simulatedPhotons/`
- `<output_root>/<runname>/transportedPhotons/`
- `<output_root>/<runname>/macros/`

### 3.2 HDF5 structure

HDF5 mode writes normalized datasets:

- `/primaries`
- `/secondaries`
- `/photons`

Dataset columns:

- `/primaries`: `gun_call_id`, `primary_track_id`, `primary_species`, `primary_x_mm`, `primary_y_mm`, `primary_energy_MeV`
- `/secondaries`: `gun_call_id`, `primary_track_id`, `secondary_track_id`, `secondary_species`, `secondary_origin_x_mm`, `secondary_origin_y_mm`, `secondary_origin_z_mm`, `secondary_origin_energy_MeV`
- `/photons`: `gun_call_id`, `primary_track_id`, `secondary_track_id`, `photon_track_id`, `photon_origin_x_mm`, `photon_origin_y_mm`, `photon_origin_z_mm`, `photon_scint_exit_x_mm`, `photon_scint_exit_y_mm`, `photon_scint_exit_z_mm`, `optical_interface_hit_x_mm`, `optical_interface_hit_y_mm`, `optical_interface_hit_dir_x`, `optical_interface_hit_dir_y`, `optical_interface_hit_dir_z`, `optical_interface_hit_pol_x`, `optical_interface_hit_pol_y`, `optical_interface_hit_pol_z`, `optical_interface_hit_energy_eV`, `optical_interface_hit_wavelength_nm`

`/photons` captures both geometric and optical state at the crossing point (position, direction, polarization, energy, wavelength) so downstream ray tracing does not need to reconstruct those values.

## 4. Useful Things to Know About the Code

- Random seeding:
  - Runs use fresh random seeds by default.
  - For reproducibility, set seeds in macro before `/run/beamOn`:
    - `/random/setSeeds 12345 67890`

- Geometry/output messenger commands:
  - Use `/scintillator/geom/*`, `/optical_interface/geom/*`, and `/output/*` to configure simulation from macro files.
  - After changing geometry commands, run `/run/initialize` before `/run/beamOn`.

- Directory creation behavior:
  - C++ runtime does not create parent output directories.
  - Directory creation is handled in Python (`src/config/ConfigIO.py`).
  - If output parent directories are missing at run start, simulation aborts with a fatal error.

- Optical physics check:
  - In Geant4 prompt, run `/run/initialize` then `/process/list`.
  - Expect optical processes such as `Scintillation`, `OpAbsorption`, and `OpBoundary`.

- HDF5 schema updates:
  - Existing HDF5 files are not migrated in-place.
  - To use newer `/photons` schema fields, write to a fresh file (new runname or new path).

- Code map:
  - Core Geant4 app: `sim/src/`, headers in `sim/include/`, macros in `sim/macros/`
  - Python config/model layer: `src/config/`
  - Lens model parsing: `src/optics/LensModels.py`
