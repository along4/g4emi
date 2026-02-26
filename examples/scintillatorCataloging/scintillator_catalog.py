"""YAML-driven scintillator catalog override example macro generator.

This example follows the strict `Metadata.RunEnvironment` layout:
- `WorkingDirectory` + `SimulationRunID` define the run root.
- `MacroDirectory` controls macro staging under the run root.
- `LogDirectory` controls log/config staging under the run root.
- `OutputInfo` controls per-stage output directories under the run root.

Directory creation is intentionally handled in Python before Geant4 starts.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure repository root is importable when this file is run directly.
# This keeps example scripts runnable without installing the package.
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.config.ConfigIO import (  # noqa: E402
    from_yaml,
    resolve_run_environment_paths,
    write_macro,
)

# Default YAML example in this directory.
EXAMPLE_YAML_PATH = Path(__file__).with_name("EJ200.yaml")


def main() -> None:
    """Generate a runnable catalog-override macro from YAML settings.

    Step-by-step:
    1. Build validated `SimConfig` via `from_yaml(...)`.
    2. Write macro and prepare run-environment directories in Python.
    3. Resolve canonical run-environment paths for reporting.
    4. Print canonical run-environment paths for reproducible invocation.
    """

    # Use optional CLI YAML path; default to local EJ200 example.
    yaml_path = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else EXAMPLE_YAML_PATH.resolve()
    )

    # Parse + validate simulation schema, including catalog hydration
    # (catalogId -> scintillator properties) handled inside ConfigIO.
    config = from_yaml(yaml_path)

    # Write macro text from validated config.
    # This call also prepares run-environment directories in Python.
    write_macro(
        config,
        include_output=True,
        include_run_initialize=True,
        overwrite=True,
    )
    paths = resolve_run_environment_paths(config)
    macro_path = paths.macro_file

    # Emit explicit paths so users can copy/paste the run command and know
    # exactly where outputs are expected to appear.
    print(f"Loaded YAML: {yaml_path}")
    print(f"Run root: {paths.run_root}")
    print(f"Wrote macro: {macro_path}")
    print(f"Output stage directory: {paths.simulated_photons}")
    print(f"Log directory: {paths.log}")
    print(f"Transport stage directory: {paths.transported_photons}")
    print(
        "Expected HDF5 target: "
        f"{paths.simulated_photons / 'photon_optical_interface_hits.h5'}"
    )
    print(
        "Expected transport target: "
        f"{paths.transported_photons / 'photons_intensifier_hits.h5'}"
    )
    print(f"Run with: pixi run g4emi {macro_path}")


if __name__ == "__main__":
    main()
