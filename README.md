# Scintillator + Neutron GPS (Geant4)

This minimal Geant4 app builds a simple setup:

- World: air box (`1 m` side)
- Target: scintillator slab (`5 cm x 5 cm x 1 cm`, custom material `EJ200`)
- Source: `G4GeneralParticleSource` configured by macro to shoot neutrons toward the slab
- Physics: `FTFP_BERT_HP` + `G4OpticalPhysics` (enables scintillation optical photons)

During a run, the code prints progress every 1000 events.
Optical photons crossing a thin optical-interface plane at the scintillator back face are recorded to
CSV, HDF5, or both (selectable).

## Build

Make sure your Geant4 environment is loaded first (for both CMake discovery and runtime libraries).

Example for this machine:

```bash
source /opt/geant4/geant4-v11.2.1/install/bin/geant4.sh
```

```bash
cmake -S . -B build
cmake --build build -j
```

## Python Environment (Pixi + ray-optics)

This repository includes a `pixi.toml` for Python optics analysis workflows.

Create the environment:

```bash
pixi install
```

Verify the `ray-optics` import:

```bash
pixi run check-ray-optics
```

Open an interactive Python REPL inside the Pixi environment:

```bash
pixi run python-repl
```

## Python Geometry Config Module

`src/config/SimConfig.py` is an import-only module (no CLI entrypoint). It
handles validated geometry + lens metadata.

`src/config/ConfigIO.py` owns macro load/save operations for `SimConfig`.

Canon 50mm preset behavior:

- Scintillator: `10 cm x 10 cm x 2 cm`
- Optical-interface standoff: `20 cm` from scintillator back face to optical-interface front face
- Optical-interface diameter: derived from `src/optics/zmxFiles/CanonEF50mmf1.0L.zmx`

Use it from Python code:

```python
from src.config.ConfigIO import apply_geometry_to_macro
from src.config.SimConfig import SimConfig

cfg = SimConfig(lenses=["canon50"], reversed=False)
print(cfg.geometry_commands())
apply_geometry_to_macro(cfg, "sim/macros/microscope_run.mac")
```

Load from an existing macro, then write a new macro from scratch:

```python
from src.config.ConfigIO import from_macro, write_macro

loaded = from_macro(
    "sim/macros/microscope_run.mac",
    lenses=["canon50"],
    reversed=False,
)
write_macro(loaded, "sim/macros/generated_from_config.mac")
```

## Run (batch GPS neutrons)

```bash
./build/g4emi sim/macros/neutron_gps.mac
```

## Random Seeding

By default, the app auto-generates fresh master random seeds on every launch.
This makes independent runs produce different random trajectories by default.

If you need reproducible runs, explicitly set seeds in your macro before `/run/beamOn`:

```text
/random/setSeeds 12345 67890
```

## Configuration via Messenger (`/scintillator/geom/...` + `/optical_interface/geom/...` + `/output/...`)

The app now exposes UI commands so you can set geometry and output directly in
macro files (or interactively) instead of relying on environment variables.

Command groups:

- `/scintillator/geom/*`: scintillator geometry/material
- `/optical_interface/geom/*`: optical-interface geometry
- `/output/*`: output format and base filename

### Supported commands

- `/output/format [csv|hdf5|both]`
- `/output/filename <base_or_path>`
- `/output/runname <name>` (optional; default empty, writes into `data/<runname>/`)
- `/scintillator/geom/material <name>` (e.g. `EJ200` or a NIST material name)
- `/scintillator/geom/scintX <value> <unit>`
- `/scintillator/geom/scintY <value> <unit>`
- `/scintillator/geom/scintZ <value> <unit>`
- `/scintillator/geom/posX <value> <unit>`
- `/scintillator/geom/posY <value> <unit>`
- `/scintillator/geom/posZ <value> <unit>`
- `/optical_interface/geom/sizeX <value> <unit>` (0 means inherit scintillator X)
- `/optical_interface/geom/sizeY <value> <unit>` (0 means inherit scintillator Y)
- `/optical_interface/geom/thickness <value> <unit>`
- `/optical_interface/geom/posX <value> <unit>`
- `/optical_interface/geom/posY <value> <unit>`
- `/optical_interface/geom/posZ <value> <unit>` (optional; if unset, defaults to flush on scintillator +Z face)

After changing geometry commands, run:

```text
/run/initialize
```

before `/run/beamOn`.

### Example config macro snippet

```text
/output/format both
/output/filename data/photon_optical_interface_hits

/scintillator/geom/material EJ200
/scintillator/geom/scintX 5 cm
/scintillator/geom/scintY 5 cm
/scintillator/geom/scintZ 1 cm
/scintillator/geom/posX 0 cm
/scintillator/geom/posY 0 cm
/scintillator/geom/posZ 0 cm
/optical_interface/geom/sizeX 5 cm
/optical_interface/geom/sizeY 5 cm
/optical_interface/geom/thickness 0.1 mm
/optical_interface/geom/posX 0 cm
/optical_interface/geom/posY 0 cm
# /optical_interface/geom/posZ 5 mm  # optional absolute Z override (otherwise flush default)
/run/initialize
```

## Run (interactive UI/vis)

```bash
./build/g4emi
```

This uses `sim/macros/vis.mac` on startup.

## Verify optical scintillation physics is active

In the Geant4 prompt:

```text
/run/initialize
/process/list
```

You should see optical processes such as `Scintillation`, `OpAbsorption`, and `OpBoundary`.

## Photon Optical-Interface Output

CSV mode: each row in `data/photon_optical_interface_hits.csv` represents one optical photon that reached
the back-face optical-interface.

### File location (all output modes)

Output files are written under the repository data directory (`<repo>/data`) regardless of launch directory.

- Outputs are written to `./data/photon_optical_interface_hits.csv` and/or `./data/photon_optical_interface_hits.h5` (repo root).
- If `/output/runname <name>` is set, outputs are written to `./data/<name>/photon_optical_interface_hits.csv` and/or `./data/<name>/photon_optical_interface_hits.h5`.

### Column schema

`data/photon_optical_interface_hits.csv` columns in order:

| Column | Type | Units | Meaning | Notes |
|---|---|---|---|---|
| `event_id` | integer | n/a | Geant4 event index for this run | Starts at `0` and increments per event in `/run/beamOn N`. |
| `primary_id` | integer | n/a | Track ID of the root primary associated with this photon hit | Track IDs are event-local. Commonly `1` when one primary is generated per event. |
| `secondary_id` | integer | n/a | Track ID of the optical photon's immediate parent track | Usually a recoil/charged secondary that produced scintillation. |
| `photon_id` | integer | n/a | Track ID of the optical photon that reached the optical-interface | Unique within an event, not across the entire file. |
| `prim_spec` | string | n/a | Species label of the primary particle | Examples: `n`, `g`, `a`, `p`, `electron`, `positron`. |
| `prim_x` | float | mm | Primary vertex x-position | Position of the primary vertex used for that event. |
| `prim_y` | float | mm | Primary vertex y-position | Position of the primary vertex used for that event. |
| `sec_spec` | string | n/a | Species label of optical photon's parent track | Example values include `p`, `C12`, `electron`, etc. |
| `sec_origin_x` | float | mm | Parent-track vertex x-position | Where the parent track was created. |
| `sec_origin_y` | float | mm | Parent-track vertex y-position | Where the parent track was created. |
| `sec_origin_z` | float | mm | Parent-track vertex z-position | Where the parent track was created. |
| `sec_origin_eng` | float | MeV | Parent-track kinetic energy at creation | This is track origin energy, not energy at photon emission step. |
| `scin_orig_x` | float | mm | Optical-photon origin x-position in scintillator | Captured at photon creation. |
| `scin_orig_y` | float | mm | Optical-photon origin y-position in scintillator | Captured at photon creation. |
| `scin_orig_z` | float | mm | Optical-photon origin z-position in scintillator | Captured at photon creation. |
| `scin_face_x` | float | mm | Optical-photon hit x-position at back-face optical-interface | Position at optical-interface crossing point. |
| `scin_face_y` | float | mm | Optical-photon hit y-position at back-face optical-interface | Position at optical-interface crossing point. |

Practical uniqueness keys:

- Primary track key: `(event_id, primary_id)`
- Secondary track key: `(event_id, secondary_id)`
- Photon track key: `(event_id, photon_id)`

### Units

- Positions are in `mm`
- `sec_origin_eng` is in `MeV`

### Critical ID semantics

- `event_id` is the Geant4 event index for that run (`0..N-1` for `/run/beamOn N`).
- `primary_id`, `secondary_id`, and `photon_id` are Geant4 track IDs.
- Track IDs are unique within a single event, not globally across all events.
- Track IDs reset every event.

This means:

- `primary_id` often appears as `1` in many rows when there is one primary/event.
- Repeated `(primary_id, secondary_id)` pairs across the full CSV are normal.
- To identify a unique track globally in the file, use `(event_id, track_id)`.

### Why `primary_id` is usually `1` here

Current macro (`sim/macros/neutron_gps.mac`) generates one primary neutron per event
(default GPS behavior, no `/gps/number` set).

So typically:

- Root primary neutron track in each event has `primary_id = 1`.
- Optical photons then descend from secondary tracks such as `2`, `3`, `4`, etc.

### What changes if `/gps/number` is set

If you add:

```text
/gps/number 2
```

each event starts with 2 primary neutrons instead of 1.

Then, for one `event_id`, you can see multiple root primary tracks (for example
`primary_id=1` and `primary_id=2`).

### Interpreting repeated IDs correctly

Bad comparison (ambiguous):

- Compare all rows with `primary_id=1` across the entire file.

Correct comparison:

- Compare rows by both `event_id` and `primary_id`.
- Example key for primary track: `(event_id, primary_id)`.
- Example key for secondary track: `(event_id, secondary_id)`.
- Example key for photon track: `(event_id, photon_id)`.

### Quick inspection commands

Show header and first rows:

```bash
head -n 6 data/photon_optical_interface_hits.csv
```

Show one event only:

```bash
awk -F, 'NR==1 || $1==0' data/photon_optical_interface_hits.csv | head -n 20
```

Count rows per event:

```bash
awk -F, 'NR>1{c[$1]++} END{for(e in c) print e,c[e]}' data/photon_optical_interface_hits.csv | sort -n | head
```

Check distinct secondary IDs for one event (example `event_id=0`):

```bash
awk -F, '$1==0{print $3}' data/photon_optical_interface_hits.csv | sort -n | uniq
```

## HDF5 layout

HDF5 mode writes normalized datasets (less repetition than flat CSV):

- `/primaries`
- `/secondaries`
- `/photons`

Dataset schemas:

- `/primaries`: `gun_call_id`, `primary_track_id`, `primary_species`,
  `primary_x_mm`, `primary_y_mm`, `primary_energy_MeV`
- `/secondaries`: `gun_call_id`, `primary_track_id`, `secondary_track_id`,
  `secondary_species`, `secondary_origin_x_mm`, `secondary_origin_y_mm`,
  `secondary_origin_z_mm`, `secondary_origin_energy_MeV`
- `/photons`: `gun_call_id`, `primary_track_id`, `secondary_track_id`,
  `photon_track_id`, `photon_origin_x_mm`, `photon_origin_y_mm`,
  `photon_origin_z_mm`, `optical_interface_hit_x_mm`, `optical_interface_hit_y_mm`,
  `optical_interface_hit_dir_x`, `optical_interface_hit_dir_y`, `optical_interface_hit_dir_z`,
  `optical_interface_hit_pol_x`, `optical_interface_hit_pol_y`, `optical_interface_hit_pol_z`,
  `optical_interface_hit_energy_eV`, `optical_interface_hit_wavelength_nm`

### `/photons` optical-interface crossing fields

The `/photons` dataset now stores enough optical state at the optical-interface crossing
to seed downstream lens propagation in external tools (e.g. Python ray tracing).

| Field | Units | Meaning |
|---|---|---|
| `optical_interface_hit_x_mm` | mm | Optical-interface entry position x at pre-step boundary crossing. |
| `optical_interface_hit_y_mm` | mm | Optical-interface entry position y at pre-step boundary crossing. |
| `optical_interface_hit_dir_x` | unitless | x-component of momentum direction unit vector at crossing. |
| `optical_interface_hit_dir_y` | unitless | y-component of momentum direction unit vector at crossing. |
| `optical_interface_hit_dir_z` | unitless | z-component of momentum direction unit vector at crossing. |
| `optical_interface_hit_pol_x` | unitless | x-component of photon polarization vector at crossing. |
| `optical_interface_hit_pol_y` | unitless | y-component of photon polarization vector at crossing. |
| `optical_interface_hit_pol_z` | unitless | z-component of photon polarization vector at crossing. |
| `optical_interface_hit_energy_eV` | eV | Photon total energy at optical-interface crossing. |
| `optical_interface_hit_wavelength_nm` | nm | Photon wavelength derived as `lambda = h*c/E` from crossing energy. |

Notes:

- Direction and polarization components are written in world coordinates.
- `optical_interface_hit_energy_eV` and `optical_interface_hit_wavelength_nm` are both stored so
  post-processing does not need to recompute spectral values.
- CSV output remains unchanged; these new fields are HDF5-only in `/photons`.

Naming semantics:

- `gun_call_id` is the event index (`G4Event::GetEventID()`), i.e. the n-th time
  the primary generator was invoked for an event.
- `*_track_id` fields are Geant4 track IDs and are unique only within a single
  `gun_call_id`.

Important interpretation note:

- `/primaries` has one row per event (every `gun_call_id`).
- `/secondaries` and `/photons` are sparse: they only contain rows linked to
  detected photons at the back-face optical-interface, so some `gun_call_id` values are
  intentionally absent there.

Units are the same as CSV:

- Positions in `mm`
- Energies in `/primaries` and `/secondaries` are in `MeV`
- Photon crossing energy in `/photons` is in `eV`
- Photon crossing wavelength in `/photons` is in `nm`
- Direction and polarization components are unitless

### HDF5 schema update behavior

HDF5 compound datasets are not migrated in-place.

- If you append to an existing older `photon_optical_interface_hits.h5`, it keeps the old
  `/photons` compound layout.
- To get the new `/photons` fields, write to a fresh file:
  use a new `/output/runname`, or remove/rename the existing HDF5 file first.
