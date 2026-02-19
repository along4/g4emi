"""YAML and macro IO helpers for hierarchical :mod:`src.config.SimConfig`.

This module owns:
- YAML file loading/writing for validated `SimConfig` objects.
- Deterministic Geant4 macro command generation from nested config fields.
- Output/log/macro directory resolution and creation.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

try:
    from src.config.SimConfig import SimConfig
    from src.config.utilsConfig import resolve_path
except ModuleNotFoundError:
    # Support imports when repository root is not already on sys.path.
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from src.config.SimConfig import SimConfig
    from src.config.utilsConfig import resolve_path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - dependency availability varies
    yaml = None


SIMULATED_PHOTONS_STAGE_DIR = "simulatedPhotons"
TRANSPORT_PHOTONS_STAGE_DIR = "transportPhotons"
MACROS_STAGE_DIR = "macros"
DEFAULT_GENERATED_MACRO_FILENAME = "generated_from_config.mac"
DEFAULT_OUTPUT_FILENAME_BASE = "photon_optical_interface_hits"
DEFAULT_OPTICAL_INTERFACE_THICKNESS_MM = 0.1


def _require_yaml_dependency() -> Any:
    """Return PyYAML module or raise a clear dependency error."""

    if yaml is None:
        raise ModuleNotFoundError(
            "PyYAML is required for YAML config IO. "
            "Install it in your environment (for example: pixi add pyyaml)."
        )
    return yaml


def load_yaml_mapping(yaml_path: str | Path) -> dict[str, Any]:
    """Load and validate a top-level YAML mapping/object."""

    module_yaml = _require_yaml_dependency()
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"YAML config file not found: {path}")

    parsed = module_yaml.safe_load(path.read_text(encoding="utf-8"))
    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        raise ValueError(f"YAML config at {path} must be a mapping/object at top level.")
    return parsed


def _extract_sim_config_payload(parsed: dict[str, Any]) -> dict[str, Any]:
    """Extract top-level keys recognized by `SimConfig`.

    This intentionally allows script-level extras to coexist in one YAML file.
    """

    accepted_keys = set(SimConfig.model_fields.keys()) | {"Metadata"}
    return {key: value for key, value in parsed.items() if key in accepted_keys}


def from_yaml(yaml_path: str | Path) -> SimConfig:
    """Load and validate a :class:`SimConfig` from YAML.

    Extra top-level keys are ignored so callers can keep script-level settings
    in the same YAML file.
    """

    parsed = load_yaml_mapping(yaml_path)
    return SimConfig.model_validate(_extract_sim_config_payload(parsed))


def write_yaml(
    config: SimConfig,
    yaml_path: str | Path,
    *,
    overwrite: bool = True,
) -> None:
    """Write a :class:`SimConfig` to a YAML file."""

    module_yaml = _require_yaml_dependency()
    path = Path(yaml_path)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")

    payload: dict[str, Any] = config.model_dump(mode="python", by_alias=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        module_yaml.safe_dump(payload, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _working_directory(config: SimConfig) -> Path:
    """Resolve `Metadata.WorkingDirectory` to an absolute path."""

    return resolve_path(config.metadata.working_directory)


def resolve_data_directory(config: SimConfig) -> Path:
    """Resolve `Metadata.OutputInfo.DataDirectory` against working directory."""

    return resolve_path(
        config.metadata.output_info.data_directory,
        base_directory=_working_directory(config),
    )


def resolve_log_directory(config: SimConfig) -> Path:
    """Resolve `Metadata.OutputInfo.LogDirectory` against working directory."""

    return resolve_path(
        config.metadata.output_info.log_directory,
        base_directory=_working_directory(config),
    )


def _run_root(config: SimConfig) -> Path:
    """Resolve run root as `<data-directory>/<SimulationRunID>/`."""

    run_id = config.metadata.simulation_run_id.strip()
    if not run_id:
        return resolve_data_directory(config)
    return (resolve_data_directory(config) / run_id).resolve()


def resolve_output_stage_directory(config: SimConfig) -> Path:
    """Resolve simulation output stage directory path."""

    return (_run_root(config) / SIMULATED_PHOTONS_STAGE_DIR).resolve()


def resolve_transport_photons_stage_directory(config: SimConfig) -> Path:
    """Resolve transport-photons stage directory path."""

    return (_run_root(config) / TRANSPORT_PHOTONS_STAGE_DIR).resolve()


def resolve_macro_stage_directory(config: SimConfig) -> Path:
    """Resolve macro stage directory path."""

    return (_run_root(config) / MACROS_STAGE_DIR).resolve()


def resolve_default_macro_path(config: SimConfig) -> Path:
    """Resolve default macro output path for `write_macro(..., macro_path=None)`."""

    run_name = config.metadata.simulation_run_id.strip()
    macro_filename = (
        f"{run_name}.mac" if run_name else DEFAULT_GENERATED_MACRO_FILENAME
    )
    return (resolve_macro_stage_directory(config) / macro_filename).resolve()


def _normalize_output_format_token(value: str) -> str:
    """Normalize output format token to Geant4 command-compatible text."""

    token = value.strip().lower()
    if token == "h5":
        return "hdf5"
    return token


def output_commands(config: SimConfig) -> list[str]:
    """Return output control command lines for a validated config."""

    return [
        f"/output/format {_normalize_output_format_token(config.metadata.output_info.output_format)}",
        f"/output/path {resolve_data_directory(config)}",
        f"/output/filename {DEFAULT_OUTPUT_FILENAME_BASE}",
        f"/output/runname {config.metadata.simulation_run_id}",
    ]


def _resolve_sensitive_detector_diameter_mm(config: SimConfig) -> float:
    """Resolve sensitive-detector diameter from configured diameter rule."""

    geometry = config.optical.geometry
    rule = config.optical.sensitive_detector_config.diameter_rule.replace(" ", "")

    if rule == "min(entranceDiameter,sensorMaxWidth)":
        return min(geometry.entrance_diameter, geometry.sensor_max_width)
    if rule == "entranceDiameter":
        return geometry.entrance_diameter
    if rule == "sensorMaxWidth":
        return geometry.sensor_max_width

    raise ValueError(
        "Unsupported `optical.sensitiveDetectorConfig.diameterRule`: "
        f"{config.optical.sensitive_detector_config.diameter_rule!r}. "
        "Supported rules: min(entranceDiameter,sensorMaxWidth), entranceDiameter, sensorMaxWidth."
    )


def geometry_commands(config: SimConfig) -> list[str]:
    """Build Geant4 geometry command lines from hierarchical config."""

    scint = config.scintillator
    optical = config.optical
    detector = optical.sensitive_detector_config

    commands = [
        f"/scintillator/geom/material {scint.properties.name}",
        f"/scintillator/geom/scintX {scint.dimension_mm.x_mm:g} mm",
        f"/scintillator/geom/scintY {scint.dimension_mm.y_mm:g} mm",
        f"/scintillator/geom/scintZ {scint.dimension_mm.z_mm:g} mm",
        f"/scintillator/geom/posX {scint.position_mm.x_mm:g} mm",
        f"/scintillator/geom/posY {scint.position_mm.y_mm:g} mm",
        f"/scintillator/geom/posZ {scint.position_mm.z_mm:g} mm",
    ]

    if detector.shape.strip().lower() == "circle":
        aperture_radius_mm = 0.5 * _resolve_sensitive_detector_diameter_mm(config)
        commands.append(f"/scintillator/geom/apertureRadius {aperture_radius_mm:g} mm")

    commands.extend(
        [
            f"/optical_interface/geom/sizeX {optical.geometry.entrance_diameter:g} mm",
            f"/optical_interface/geom/sizeY {optical.geometry.entrance_diameter:g} mm",
            f"/optical_interface/geom/thickness {DEFAULT_OPTICAL_INTERFACE_THICKNESS_MM:g} mm",
            f"/optical_interface/geom/posX {detector.position_mm.x_mm:g} mm",
            f"/optical_interface/geom/posY {detector.position_mm.y_mm:g} mm",
            f"/optical_interface/geom/posZ {detector.position_mm.z_mm:g} mm",
        ]
    )
    return commands


def ensure_output_directories(config: SimConfig) -> Path:
    """Create and return the simulation output stage directory.

    Creates:
    - output stage: `<data>/<run-id>/simulatedPhotons/`
    - transport stage: `<data>/<run-id>/transportPhotons/`
    - log directory from `Metadata.OutputInfo.LogDirectory`
    """

    output_stage_dir = resolve_output_stage_directory(config)
    output_stage_dir.mkdir(parents=True, exist_ok=True)

    transport_stage_dir = resolve_transport_photons_stage_directory(config)
    transport_stage_dir.mkdir(parents=True, exist_ok=True)

    log_dir = resolve_log_directory(config)
    log_dir.mkdir(parents=True, exist_ok=True)

    return output_stage_dir


def ensure_macro_directories(config: SimConfig) -> Path:
    """Create and return the macros stage directory for this config."""

    macro_stage_dir = resolve_macro_stage_directory(config)
    macro_stage_dir.mkdir(parents=True, exist_ok=True)
    return macro_stage_dir


def macro_commands(
    config: SimConfig,
    *,
    include_output: bool = True,
    include_run_initialize: bool = True,
) -> list[str]:
    """Build a macro command block from config state."""

    commands: list[str] = []
    if include_output:
        commands.extend(output_commands(config))
    commands.extend(geometry_commands(config))
    if include_run_initialize:
        commands.append("/run/initialize")
    return commands


def write_macro(
    config: SimConfig,
    macro_path: str | Path | None = None,
    *,
    include_output: bool = True,
    include_run_initialize: bool = True,
    create_output_directories: bool = True,
    overwrite: bool = True,
) -> None:
    """Write a Geant4 macro file from config."""

    path = resolve_default_macro_path(config) if macro_path is None else Path(macro_path)

    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")

    if create_output_directories:
        ensure_output_directories(config)
        ensure_macro_directories(config)

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(
        macro_commands(
            config,
            include_output=include_output,
            include_run_initialize=include_run_initialize,
        )
    )
    path.write_text(payload + "\n", encoding="utf-8")


def append_macro_commands(
    macro_path: str | Path,
    commands: Any,
    *,
    key_name: str = "commands",
) -> None:
    """Append command lines to an existing macro file."""

    path = Path(macro_path)
    if not path.exists():
        raise FileNotFoundError(f"Macro file not found: {path}")
    if not isinstance(commands, list) or not all(
        isinstance(item, str) for item in commands
    ):
        raise ValueError(f"YAML key `{key_name}` must be a list of strings.")
    if not commands:
        return

    body = path.read_text(encoding="utf-8")
    sep = "" if body.endswith("\n") else "\n"
    path.write_text(body + sep + "\n".join(commands) + "\n", encoding="utf-8")
