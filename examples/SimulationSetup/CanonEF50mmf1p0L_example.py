"""YAML-driven CanonEF50mmf1p0L macro generator.

This script:
1. Writes the standard batch macro from YAML.
2. Writes a mask-visualization macro.
3. Prints interactive Geant4 commands to load the mask-visualization macro.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure repository root is importable when this file is run directly.
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.common.logger import configure_run_logger, get_logger  # noqa: E402
from src.config.ConfigIO import (  # noqa: E402
    append_macro_line,
    from_yaml,
    geometry_commands,
    resolve_run_environment_paths,
    write_macro,
)

# Hard-coded Canon example YAML path.
EXAMPLE_YAML_PATH = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "yamlFiles"
    / "CanonEF50mmf1p0L_example.yaml"
)


def main() -> None:
    """Generate Canon macros and print interactive run instructions.

    Step-by-step:
    1. Build validated `SimConfig` via `from_yaml(...)`.
    2. Write standard batch macro and mask-visualization macro.
    3. Resolve canonical run-environment paths for reporting.
    4. Print interactive Geant4 commands for mask visualization.
    """

    config = from_yaml(EXAMPLE_YAML_PATH.resolve())
    log_path = configure_run_logger(config)
    logger = get_logger()

    write_macro(
        config,
        include_output=True,
        include_run_initialize=True,
        overwrite=True,
    )
    paths = resolve_run_environment_paths(config)
    batch_macro_path = paths.macro_file
    mask_vis_macro_path = paths.macro / f"{batch_macro_path.stem}_mask_vis.mac"
    mask_vis_macro_path.write_text("", encoding="utf-8")

    append_macro_line(mask_vis_macro_path, "/control/verbose 1")
    append_macro_line(mask_vis_macro_path, "/run/verbose 1")
    append_macro_line(mask_vis_macro_path, "/event/verbose 0")
    append_macro_line(mask_vis_macro_path, "/tracking/verbose 0")
    append_macro_line(mask_vis_macro_path, "/tracking/storeTrajectory 1")
    for command in geometry_commands(config):
        append_macro_line(mask_vis_macro_path, command)
    append_macro_line(mask_vis_macro_path, "/run/initialize")
    append_macro_line(mask_vis_macro_path, "/vis/open OGL")
    append_macro_line(mask_vis_macro_path, "/vis/drawVolume")
    append_macro_line(mask_vis_macro_path, "/vis/viewer/set/style wireframe")
    append_macro_line(mask_vis_macro_path, "/vis/viewer/set/hiddenEdge 0")
    append_macro_line(mask_vis_macro_path, "/vis/viewer/set/viewpointThetaPhi 110 20")
    append_macro_line(mask_vis_macro_path, "/vis/viewer/zoom 3")
    append_macro_line(mask_vis_macro_path, "/vis/scene/add/axes 0 0 0 20 mm")
    append_macro_line(mask_vis_macro_path, "/vis/scene/add/trajectories")
    append_macro_line(
        mask_vis_macro_path, "/vis/modeling/trajectories/create/drawByParticleID"
    )
    append_macro_line(
        mask_vis_macro_path,
        "/vis/modeling/trajectories/drawByParticleID-0/set neutron red",
    )
    append_macro_line(
        mask_vis_macro_path,
        "/vis/modeling/trajectories/drawByParticleID-0/set opticalphoton yellow",
    )
    append_macro_line(
        mask_vis_macro_path,
        "/vis/modeling/trajectories/drawByParticleID-0/default/setDrawStepPts false",
    )
    append_macro_line(mask_vis_macro_path, "/vis/scene/endOfEventAction accumulate 20")
    append_macro_line(mask_vis_macro_path, "/vis/viewer/set/autoRefresh true")
    append_macro_line(mask_vis_macro_path, "/vis/viewer/rebuild")
    append_macro_line(mask_vis_macro_path, "/vis/viewer/refresh")

    logger.info(f"Run log: {log_path}")
    logger.info(f"Loaded YAML: {EXAMPLE_YAML_PATH.resolve()}")
    logger.info(f"Wrote batch macro: {batch_macro_path}")
    logger.info(f"Wrote mask-vis macro: {mask_vis_macro_path}")
    logger.info(f"Mask radius (mm): {config.scintillator.mask_radius_mm:g}")
    logger.info(f"Output stage directory: {paths.simulated_photons}")
    logger.info(
        "Expected HDF5 target: "
        f"{paths.simulated_photons / 'photon_optical_interface_hits.h5'}"
    )
    logger.info("Start Geant4 interactively:")
    logger.info("  pixi run g4emi")
    logger.info("Then in the Geant4 prompt execute:")
    logger.info(f"  /control/execute {mask_vis_macro_path}")


if __name__ == "__main__":
    main()
