# Scintillator + Neutron GPS (Geant4)

This minimal Geant4 app builds a simple setup:

- World: air box (`1 m` side)
- Target: scintillator slab (`5 cm x 5 cm x 1 cm`, custom material `EJ200`)
- Source: `G4GeneralParticleSource` configured by macro to shoot neutrons toward the slab
- Physics: `FTFP_BERT_HP` + `G4OpticalPhysics` (enables scintillation optical photons)

During a run, the code prints progress every 1000 events.
Optical photons crossing a thin sensor plane at the scintillator back face are recorded to
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

## Configuration via Messenger (`/scintillator/geom/...` + `/output/...`)

The app now exposes UI commands so you can set geometry and output directly in
macro files (or interactively) instead of relying on environment variables.

Command groups:

- `/scintillator/geom/*`: geometry/material
- `/output/*`: output format and base filename

### Supported commands

- `/output/format [csv|hdf5|both]`
- `/output/filename <base_or_path>`
- `/scintillator/geom/material <name>` (e.g. `EJ200` or a NIST material name)
- `/scintillator/geom/scintX <value> <unit>`
- `/scintillator/geom/scintY <value> <unit>`
- `/scintillator/geom/scintZ <value> <unit>`
- `/scintillator/geom/sensorThickness <value> <unit>`

After changing geometry commands, run:

```text
/run/initialize
```

before `/run/beamOn`.

### Example config macro snippet

```text
/output/format both
/output/filename data/photon_sensor_hits

/scintillator/geom/material EJ200
/scintillator/geom/scintX 5 cm
/scintillator/geom/scintY 5 cm
/scintillator/geom/scintZ 1 cm
/scintillator/geom/sensorThickness 0.1 mm
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

## Photon Sensor Output

CSV mode: each row in `data/data/photon_sensor_hits.csv` represents one optical photon that reached
the back-face sensor.

### File location (all output modes)

Output files are written to the current working directory of the process.

- If you run `./build/g4emi ...` from project root, file is at
  `./data/data/photon_sensor_hits.csv` and/or `./data/photon_sensor_hits.h5`.
- If you `cd build` and run `./g4emi ...`, file is at
  `./build/data/data/photon_sensor_hits.csv` and/or `./build/data/photon_sensor_hits.h5`
  (relative to project root).

### Column schema

`data/data/photon_sensor_hits.csv` columns in order:

| Column | Type | Units | Meaning | Notes |
|---|---|---|---|---|
| `event_id` | integer | n/a | Geant4 event index for this run | Starts at `0` and increments per event in `/run/beamOn N`. |
| `primary_id` | integer | n/a | Track ID of the root primary associated with this photon hit | Track IDs are event-local. Commonly `1` when one primary is generated per event. |
| `secondary_id` | integer | n/a | Track ID of the optical photon's immediate parent track | Usually a recoil/charged secondary that produced scintillation. |
| `photon_id` | integer | n/a | Track ID of the optical photon that reached the sensor | Unique within an event, not across the entire file. |
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
| `scin_face_x` | float | mm | Optical-photon hit x-position at back-face sensor | Position at sensor crossing point. |
| `scin_face_y` | float | mm | Optical-photon hit y-position at back-face sensor | Position at sensor crossing point. |

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
head -n 6 data/photon_sensor_hits.csv
```

Show one event only:

```bash
awk -F, 'NR==1 || $1==0' data/photon_sensor_hits.csv | head -n 20
```

Count rows per event:

```bash
awk -F, 'NR>1{c[$1]++} END{for(e in c) print e,c[e]}' data/photon_sensor_hits.csv | sort -n | head
```

Check distinct secondary IDs for one event (example `event_id=0`):

```bash
awk -F, '$1==0{print $3}' data/photon_sensor_hits.csv | sort -n | uniq
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
  `photon_origin_z_mm`, `sensor_hit_x_mm`, `sensor_hit_y_mm`

Naming semantics:

- `gun_call_id` is the event index (`G4Event::GetEventID()`), i.e. the n-th time
  the primary generator was invoked for an event.
- `*_track_id` fields are Geant4 track IDs and are unique only within a single
  `gun_call_id`.

Important interpretation note:

- `/primaries` has one row per event (every `gun_call_id`).
- `/secondaries` and `/photons` are sparse: they only contain rows linked to
  detected photons at the back-face sensor, so some `gun_call_id` values are
  intentionally absent there.

Units are the same as CSV:

- Positions in `mm`
- Energies in `MeV`
