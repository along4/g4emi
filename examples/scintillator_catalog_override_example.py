"""YAML-driven scintillator catalog override example macro generator.

Execution model
---------------
This script is the "safe launch" path for the catalog-override example.
It intentionally performs directory setup in Python before Geant4 runs.

Input YAML
----------
`examples/scintillator_catalog_override_example.yaml` contains:
1. Simulation config payload consumed by `ConfigIO.from_yaml(...)`.
2. Optional script-only key:
   - `macro_output_path`: explicit `.mac` destination override.

Output behavior
---------------
When `macro_output_path` is omitted:
- macro is written to the default run macro staging directory
  (`data/<SimulationRunID>/macros/<SimulationRunID>.mac`).
- output directories are created ahead of time so Geant4 can fail fast if
  they are not writable/existing.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure repository root is importable when this file is run directly.
# This keeps example scripts runnable without installing the package.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.config.ConfigIO import (  # noqa: E402
    ensure_output_directories,
    from_yaml,
    load_yaml_mapping,
    resolve_run_environment_directory,
    resolve_default_macro_path,
    write_macro,
)
from src.config.utilsConfig import resolve_optional_path  # noqa: E402

# Keep YAML colocated with this script for easy discovery and portability.
EXAMPLE_YAML_PATH = Path(__file__).with_suffix(".yaml")


def main() -> None:
    """Generate a runnable catalog-override macro from YAML settings.

    Step-by-step:
    1. Load raw YAML mapping (`payload`) so script-level extras are available.
    2. Build validated `SimConfig` via `from_yaml(...)`.
    3. Create expected output stage directories in Python.
    4. Resolve optional macro output override (if provided in YAML).
    5. Write macro commands with `/output/*` and `/run/initialize`.
    6. Print canonical paths for reproducible invocation.
    """

    # Raw YAML is needed for script-only keys that are intentionally not part of
    # strict `SimConfig` (for example `macro_output_path`).
    payload = load_yaml_mapping(EXAMPLE_YAML_PATH)

    # Parse + validate simulation schema, including catalog hydration
    # (catalogId -> scintillator properties) handled inside ConfigIO.
    config = from_yaml(EXAMPLE_YAML_PATH)

    # Pre-create output directories from Python.
    # C++ runtime expects these parents to exist and will abort otherwise.
    output_stage_dir = ensure_output_directories(config)

    # Resolve optional macro override path relative to repository root.
    # If missing/blank, ConfigIO default path logic will be used.
    macro_path = resolve_optional_path(
        payload.get("macro_output_path"),
        key_name="macro_output_path",
        base_directory=Path(__file__).resolve().parents[1],
    )

    # If a custom path is used, create its parent directory explicitly.
    if macro_path is not None:
        macro_path.parent.mkdir(parents=True, exist_ok=True)

    # Write macro text from validated config.
    # `create_output_directories=False` because this script already did that
    # with `ensure_output_directories(config)` above.
    write_macro(
        config,
        macro_path=macro_path,
        include_output=True,
        include_run_initialize=True,
        create_output_directories=False,
        overwrite=True,
    )

    # Report the actual macro path used (custom override vs default path).
    effective_macro_path = (
        macro_path if macro_path is not None else resolve_default_macro_path(config)
    )

    # Emit explicit paths so users can copy/paste the run command and know
    # exactly where outputs are expected to appear.
    print(f"Loaded YAML: {EXAMPLE_YAML_PATH.resolve()}")
    print(f"Wrote macro: {effective_macro_path}")
    print(f"Output stage directory: {output_stage_dir}")
    print(
        "Expected HDF5 target: "
        f"{resolve_run_environment_directory(config, 'simulated_photons') / 'photon_optical_interface_hits.h5'}"
    )
    print(f"Run with: pixi run g4emi {effective_macro_path}")


if __name__ == "__main__":
    main()
