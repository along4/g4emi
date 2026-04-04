# Intensifier Module

This document describes the `src/intensifier/` module.

The intensifier stage sits after optical transport. It takes photon hits on the
intensifier input plane and produces in-memory intensifier output events.

It is designed to be:

- physically staged
- fast enough for routine simulation work
- configured through `SimConfig`
- separate from any future sensor/readout model

## What It Does

The current intensifier model has three physics stages:

1. `photocathode.py`
2. `mcp.py`
3. `phosphor.py`

At a high level, the module does this:

1. read `/transported_photons` from optical transport output
2. convert transported photons into photoelectrons
3. amplify and spread those events through a simplified dual-stage MCP model
4. apply phosphor timing and spatial response
5. return final intensifier output events in memory

The main orchestration lives in `src/intensifier/pipeline.py`.

## Why It Is Structured This Way

The intensifier is modeled as separate stages rather than one large effective
"blob" model.

This keeps the code easier to understand and gives each stage its own
calibration parameters:

- photocathode: detection probability and timing jitter
- MCP: gain and spatial spread
- phosphor: output amplitude, delay, and blur

The implementation is still intentionally lightweight. It does not do
pore-level electron tracking or explicit phosphor-photon Monte Carlo.

## Inputs

The intensifier stage consumes optical transport output:

- transport file: `/transported_photons`
- source file: `/photons`

The I/O helpers in `src/intensifier/io.py` combine these so the intensifier
stages can work from one normalized in-memory batch.

## Outputs

The module currently returns an in-memory `IntensifierOutputBatch`.

This output is sensor-agnostic. It is meant to be passed to a later sensor
stage.

By default, no intensifier-stage HDF5 file is written.

If `intensifier.write_output_hdf5` is set to `true`, the pipeline also writes:

- `<run_root>/sensor/intensifier_output_events_<subrun>.h5`

That file contains:

- copied `/primaries`
- copied `/secondaries`
- `/intensifier_output_events`

Each output event carries:

- source/provenance IDs
- output position
- output time
- signal amplitude
- total MCP gain
- wavelength

## Configuration

All intensifier parameters are defined through `SimConfig` under
`intensifier`.

The current stage blocks are:

- `intensifier.photocathode`
- `intensifier.mcp`
- `intensifier.phosphor`

The current output-control flag is:

- `intensifier.write_output_hdf5`

### Photocathode Parameters

- `qe_wavelength_nm`
- `qe_values`
- `collection_efficiency`
- `tts_sigma_ns`

The photocathode stage uses a wavelength-dependent quantum efficiency lookup,
an overall collection efficiency, and optional timing jitter.

### MCP Parameters

- `stage1_mean_gain`
- `stage1_gain_shape`
- `stage2_mean_gain`
- `stage2_gain_shape`
- `gain_ref`
- `spread_sigma0_mm`
- `spread_gain_exponent`

The MCP stage uses independent stochastic gain for the two stages and a simple
gain-dependent spatial spread model.

### Phosphor Parameters

- `phosphor_gain`
- `decay_fast_ns`
- `decay_slow_ns`
- `fast_fraction`
- `psf_sigma_mm`

The phosphor stage converts MCP gain into output amplitude, samples a
fast/slow delay model, and applies a spatial blur.

## Example YAML Shape

```yaml
intensifier:
  model: Cricket2
  write_output_hdf5: false
  input_screen:
    image_circle_diameter_mm: 18.0
    center_mm: [0.0, 0.0]
    magnification: 1.0
  photocathode:
    qe_wavelength_nm: [350.0, 500.0, 650.0]
    qe_values: [0.15, 0.25, 0.05]
    collection_efficiency: 1.0
    tts_sigma_ns: 0.0
  mcp:
    stage1_mean_gain: 8.0
    stage1_gain_shape: 2.0
    stage2_mean_gain: 800.0
    stage2_gain_shape: 2.0
    gain_ref: 1000.0
    spread_sigma0_mm: 0.03
    spread_gain_exponent: 0.4
  phosphor:
    phosphor_gain: 1.0
    decay_fast_ns: 70.0
    decay_slow_ns: 200.0
    fast_fraction: 0.9
    psf_sigma_mm: 0.04
```

## Main Entry Points

Use `src/intensifier/pipeline.py` for high-level execution:

- `run_intensifier_pipeline(...)`
- `run_intensifier_pipeline_from_sim_config(...)`
- `intensifier_params_from_sim_config(...)`

Use the stage modules directly only if you want lower-level control:

- `src/intensifier/photocathode.py`
- `src/intensifier/mcp.py`
- `src/intensifier/phosphor.py`

## Current Scope

Included now:

- fast staged intensifier model
- `SimConfig`-driven parameters
- HDF5 input loading from optical transport output
- in-memory intensifier output events
- optional standalone intensifier output HDF5 writing

Not included yet:

- sensor/readout modeling
- detailed saturation effects
- pore-level MCP transport
- explicit phosphor-photon simulation
