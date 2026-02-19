"""YAML and macro IO helpers for hierarchical :mod:`src.config.SimConfig`.

Design goals
============
- Keep :class:`src.config.SimConfig.SimConfig` focused on schema/validation.
- Keep serialization and filesystem concerns in one place.
- Provide deterministic Geant4 macro command generation from nested config data.
- Provide flexible config creation from a user-provided macro.

What this module does
=====================
1. Load YAML into a plain mapping and validate into ``SimConfig``.
2. Write a validated ``SimConfig`` back to YAML (preserving YAML aliases).
3. Resolve data/log/macro directories from ``Metadata`` settings.
4. Build Geant4 command lists for output and geometry.
5. Write full macro files and append extra command blocks.

Conventions
===========
- Paths are resolved via ``resolve_path`` so relative paths in YAML are anchored
  consistently (repository-root by default, or explicit working-directory
  context where appropriate).
- Macro command ordering is intentional and stable to make testing and diffs
  straightforward.
"""

from __future__ import annotations

from datetime import date as DateType
import math
from pathlib import Path
import shlex
import sys
from typing import Any

try:
    from src.config.SimConfig import SimConfig, default_sim_config
    from src.config.utilsConfig import resolve_path
except ModuleNotFoundError:
    # Support imports when repository root is not already on sys.path.
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from src.config.SimConfig import SimConfig, default_sim_config
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

_LENGTH_UNIT_TO_MM: dict[str, float] = {
    "nm": 1.0e-6,
    "nanometer": 1.0e-6,
    "nanometers": 1.0e-6,
    "um": 1.0e-3,
    "micrometer": 1.0e-3,
    "micrometers": 1.0e-3,
    "mm": 1.0,
    "millimeter": 1.0,
    "millimeters": 1.0,
    "cm": 10.0,
    "centimeter": 10.0,
    "centimeters": 10.0,
    "m": 1000.0,
    "meter": 1000.0,
    "meters": 1000.0,
}


def _require_yaml_dependency() -> Any:
    """Return PyYAML module object or raise a dependency error.

    YAML support is optional at import time so that modules which only need
    path/macro helpers can still import this file in constrained environments.
    Any function that requires YAML parsing/writing calls this helper first.
    """

    if yaml is None:
        raise ModuleNotFoundError(
            "PyYAML is required for YAML config IO. "
            "Install it in your environment (for example: pixi add pyyaml)."
        )
    return yaml


def _length_to_mm(value: float, unit: str) -> float:
    """Convert Geant4-style length value/unit tokens to millimeters."""

    factor = _LENGTH_UNIT_TO_MM.get(unit.strip().lower())
    if factor is None:
        raise ValueError(f"Unsupported length unit '{unit}'.")
    return value * factor


def _parse_length_tokens(tokens: list[str], command: str) -> float:
    """Parse macro tokenized length command payload and return millimeters."""

    if len(tokens) < 3:
        raise ValueError(
            f"Command '{command}' requires '<value> <unit>' tokens, got: {tokens!r}"
        )

    try:
        value = float(tokens[1])
    except ValueError as exc:
        raise ValueError(
            f"Command '{command}' has non-numeric value token: {tokens[1]!r}"
        ) from exc

    return _length_to_mm(value, tokens[2])


def _default_import_template(macro_path: Path) -> SimConfig:
    """Return sensible baseline config used for macro-import gaps.

    Macro files do not encode every field required by hierarchical ``SimConfig``
    (for example source energy block, rich metadata, and lens descriptors). This
    baseline provides valid defaults that are then selectively overwritten by
    parsed macro commands.
    """

    payload = default_sim_config().model_dump(mode="python")
    metadata = payload["metadata"]
    output_info = metadata["output_info"]

    metadata["author"] = "Macro Import"
    metadata["date"] = DateType.today().isoformat()
    metadata["version"] = "imported"
    metadata["description"] = f"Imported from macro: {macro_path.name}"
    metadata["working_directory"] = str(macro_path.resolve().parent)
    metadata["simulation_run_id"] = macro_path.stem
    output_info["data_directory"] = "data"
    output_info["log_directory"] = "data/logs"
    output_info["output_format"] = "hdf5"

    return SimConfig.model_validate(payload)


def load_yaml_mapping(yaml_path: str | Path) -> dict[str, Any]:
    """Load a YAML file and ensure top-level mapping semantics.

    Parameters
    ----------
    yaml_path:
        Path to a YAML document.

    Returns
    -------
    dict[str, Any]
        Parsed top-level mapping.

    Raises
    ------
    FileNotFoundError
        If ``yaml_path`` does not exist.
    ValueError
        If YAML root is not a mapping/object.
    ModuleNotFoundError
        If PyYAML is unavailable.
    """

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


def from_macro(macro_path: str | Path, *, template: SimConfig | None = None) -> SimConfig:
    """Load a macro file and map recognized commands into ``SimConfig``.

    Parameters
    ----------
    macro_path:
        Path to a Geant4 macro file.
    template:
        Optional base config used for fields not encoded in macros. When
        omitted, a sensible imported default is used.

    Returns
    -------
    SimConfig
        Validated hierarchical configuration reconstructed from macro values.

    Notes
    -----
    - Macros are lossy relative to ``SimConfig``. They do not encode full source
      metadata/lens setup, so those values come from ``template`` defaults.
    - ``/output/filename`` is currently ignored because filename base is fixed by
      this pipeline.
    - If parsed optical-interface thickness differs from
      ``DEFAULT_OPTICAL_INTERFACE_THICKNESS_MM``, this function raises because
      thickness is not currently represented in ``SimConfig``.
    """

    path = Path(macro_path)
    if not path.exists():
        raise FileNotFoundError(f"Macro file not found: {path}")

    base = template if template is not None else _default_import_template(path)
    payload = base.model_dump(mode="python")

    metadata = payload["metadata"]
    output_info = metadata["output_info"]
    scintillator = payload["scintillator"]
    optical = payload["optical"]
    geometry = optical["geometry"]
    detector = optical["sensitive_detector_config"]

    entrance_diameter_mm: float | None = None
    size_x_mm: float | None = None
    size_y_mm: float | None = None
    aperture_radius_mm: float | None = None
    parsed_thickness_mm: float | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # Use shell-style tokenization so quoted output-path values are handled.
        tokens = shlex.split(line, comments=False, posix=True)
        if not tokens:
            continue

        command = tokens[0]

        if command == "/output/format" and len(tokens) >= 2:
            output_info["output_format"] = tokens[1].strip().lower()
            continue
        if command == "/output/path" and len(tokens) >= 2:
            output_info["data_directory"] = tokens[1]
            continue
        if command == "/output/runname" and len(tokens) >= 2:
            metadata["simulation_run_id"] = tokens[1]
            continue

        if command == "/scintillator/geom/material" and len(tokens) >= 2:
            scintillator["properties"]["name"] = tokens[1]
            continue
        if command == "/scintillator/geom/scintX":
            scintillator["dimension_mm"]["x_mm"] = _parse_length_tokens(tokens, command)
            continue
        if command == "/scintillator/geom/scintY":
            scintillator["dimension_mm"]["y_mm"] = _parse_length_tokens(tokens, command)
            continue
        if command == "/scintillator/geom/scintZ":
            scintillator["dimension_mm"]["z_mm"] = _parse_length_tokens(tokens, command)
            continue
        if command == "/scintillator/geom/posX":
            scintillator["position_mm"]["x_mm"] = _parse_length_tokens(tokens, command)
            continue
        if command == "/scintillator/geom/posY":
            scintillator["position_mm"]["y_mm"] = _parse_length_tokens(tokens, command)
            continue
        if command == "/scintillator/geom/posZ":
            scintillator["position_mm"]["z_mm"] = _parse_length_tokens(tokens, command)
            continue
        if command == "/scintillator/geom/apertureRadius":
            aperture_radius_mm = _parse_length_tokens(tokens, command)
            continue

        if command == "/optical_interface/geom/sizeX":
            size_x_mm = _parse_length_tokens(tokens, command)
            continue
        if command == "/optical_interface/geom/sizeY":
            size_y_mm = _parse_length_tokens(tokens, command)
            continue
        if command == "/optical_interface/geom/thickness":
            parsed_thickness_mm = _parse_length_tokens(tokens, command)
            continue
        if command == "/optical_interface/geom/posX":
            detector["position_mm"]["x_mm"] = _parse_length_tokens(tokens, command)
            continue
        if command == "/optical_interface/geom/posY":
            detector["position_mm"]["y_mm"] = _parse_length_tokens(tokens, command)
            continue
        if command == "/optical_interface/geom/posZ":
            detector["position_mm"]["z_mm"] = _parse_length_tokens(tokens, command)
            continue

    if parsed_thickness_mm is not None and not math.isclose(
        parsed_thickness_mm,
        DEFAULT_OPTICAL_INTERFACE_THICKNESS_MM,
        rel_tol=0.0,
        abs_tol=1.0e-9,
    ):
        raise ValueError(
            "Loaded macro uses optical-interface thickness "
            f"{parsed_thickness_mm:g} mm, but hierarchical SimConfig currently "
            "does not model thickness explicitly."
        )

    if size_x_mm is not None and size_y_mm is not None:
        if not math.isclose(size_x_mm, size_y_mm, rel_tol=0.0, abs_tol=1.0e-9):
            raise ValueError(
                "Loaded macro has non-circular optical-interface size: "
                f"sizeX={size_x_mm:.6f} mm, sizeY={size_y_mm:.6f} mm."
            )
        entrance_diameter_mm = size_x_mm
    elif size_x_mm is not None:
        entrance_diameter_mm = size_x_mm
    elif size_y_mm is not None:
        entrance_diameter_mm = size_y_mm

    if entrance_diameter_mm is not None:
        geometry["entrance_diameter"] = entrance_diameter_mm

    # Aperture command is represented indirectly in SimConfig through
    # detector shape + diameter rule. Choose a rule that reproduces parsed
    # aperture radius exactly.
    if aperture_radius_mm is not None:
        desired_diameter_mm = 2.0 * aperture_radius_mm
        geometry.setdefault("sensor_max_width", desired_diameter_mm)
        detector["shape"] = "circle"
        if entrance_diameter_mm is None:
            geometry["entrance_diameter"] = desired_diameter_mm
            geometry["sensor_max_width"] = desired_diameter_mm
            detector["diameter_rule"] = "min(entranceDiameter,sensorMaxWidth)"
        elif entrance_diameter_mm + 1.0e-9 >= desired_diameter_mm:
            geometry["sensor_max_width"] = desired_diameter_mm
            detector["diameter_rule"] = "min(entranceDiameter,sensorMaxWidth)"
        else:
            geometry["sensor_max_width"] = desired_diameter_mm
            detector["diameter_rule"] = "sensorMaxWidth"
    else:
        detector["shape"] = "none"
        detector["diameter_rule"] = "entranceDiameter"
        if entrance_diameter_mm is not None:
            geometry["sensor_max_width"] = entrance_diameter_mm

    return SimConfig.model_validate(payload)


def _extract_sim_config_payload(parsed: dict[str, Any]) -> dict[str, Any]:
    """Extract top-level keys recognized by `SimConfig`.

    This intentionally allows script-level extras to coexist in one YAML file.
    """

    # `SimConfig` accepts "metadata" field name internally while user YAML may
    # use aliased "Metadata". Keep both accepted at top-level extraction time.
    accepted_keys = set(SimConfig.model_fields.keys()) | {"Metadata"}
    return {key: value for key, value in parsed.items() if key in accepted_keys}


def from_yaml(yaml_path: str | Path) -> SimConfig:
    """Load and validate a :class:`SimConfig` from YAML file.

    Extra top-level keys are ignored so callers can keep script-level settings
    in the same YAML file.

    This behavior is intentional for example workflows where a single YAML file
    carries both strict simulation config and script orchestration values (such
    as appended macro command blocks).
    """

    parsed = load_yaml_mapping(yaml_path)
    return SimConfig.model_validate(_extract_sim_config_payload(parsed))


def write_yaml(
    config: SimConfig,
    yaml_path: str | Path,
    *,
    overwrite: bool = True,
) -> None:
    """Serialize and write a validated ``SimConfig`` to YAML.

    Parameters
    ----------
    config:
        Validated configuration object.
    yaml_path:
        Destination YAML path.
    overwrite:
        When ``False``, existing destination files raise ``FileExistsError``.

    Notes
    -----
    - Uses ``by_alias=True`` to preserve user-facing key aliases such as
      ``Metadata``, ``OutputInfo``, and camelCase optical/scintillator keys.
    - Uses ``sort_keys=False`` to retain a readable, model-order output layout.
    """

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
    """Resolve ``Metadata.WorkingDirectory`` into absolute path form."""

    return resolve_path(config.metadata.working_directory)


def resolve_data_directory(config: SimConfig) -> Path:
    """Resolve ``Metadata.OutputInfo.DataDirectory`` under working directory.

    Relative ``DataDirectory`` values are interpreted relative to
    ``Metadata.WorkingDirectory``.
    """

    return resolve_path(
        config.metadata.output_info.data_directory,
        base_directory=_working_directory(config),
    )


def resolve_log_directory(config: SimConfig) -> Path:
    """Resolve ``Metadata.OutputInfo.LogDirectory`` under working directory.

    Relative ``LogDirectory`` values are interpreted relative to
    ``Metadata.WorkingDirectory``.
    """

    return resolve_path(
        config.metadata.output_info.log_directory,
        base_directory=_working_directory(config),
    )


def _run_root(config: SimConfig) -> Path:
    """Resolve run root directory.

    Result is:
    - ``<data-directory>/<SimulationRunID>/`` when run id is non-empty
    - ``<data-directory>/`` when run id is blank
    """

    run_id = config.metadata.simulation_run_id.strip()
    if not run_id:
        return resolve_data_directory(config)
    return (resolve_data_directory(config) / run_id).resolve()


def resolve_output_stage_directory(config: SimConfig) -> Path:
    """Resolve output stage directory used by simulation data writers.

    Returns ``<run-root>/simulatedPhotons/``.
    """

    return (_run_root(config) / SIMULATED_PHOTONS_STAGE_DIR).resolve()


def resolve_transport_photons_stage_directory(config: SimConfig) -> Path:
    """Resolve transport stage directory.

    Returns ``<run-root>/transportPhotons/``.
    """

    return (_run_root(config) / TRANSPORT_PHOTONS_STAGE_DIR).resolve()


def resolve_macro_stage_directory(config: SimConfig) -> Path:
    """Resolve macro stage directory.

    Returns ``<run-root>/macros/``.
    """

    return (_run_root(config) / MACROS_STAGE_DIR).resolve()


def resolve_default_macro_path(config: SimConfig) -> Path:
    """Resolve default macro output path for ``write_macro(..., macro_path=None)``.

    File naming policy:
    - ``<SimulationRunID>.mac`` when run id is non-empty
    - ``generated_from_config.mac`` otherwise
    """

    run_name = config.metadata.simulation_run_id.strip()
    macro_filename = (
        f"{run_name}.mac" if run_name else DEFAULT_GENERATED_MACRO_FILENAME
    )
    return (resolve_macro_stage_directory(config) / macro_filename).resolve()


def _normalize_output_format_token(value: str) -> str:
    """Normalize output format token to Geant4 command-compatible text.

    Currently this only maps ``h5`` to ``hdf5`` and lowercases all values.
    Validation of allowed final values is delegated to runtime Geant4 command
    handling and/or higher-level config conventions.
    """

    token = value.strip().lower()
    if token == "h5":
        return "hdf5"
    return token


def output_commands(config: SimConfig) -> list[str]:
    """Build Geant4 ``/output/*`` command lines from metadata settings.

    Command mapping:
    - ``OutputInfo.OutputFormat`` -> ``/output/format``
    - resolved ``DataDirectory``  -> ``/output/path``
    - fixed base filename         -> ``/output/filename``
    - ``SimulationRunID``         -> ``/output/runname``

    The filename base is fixed so simulation artifacts remain consistently named
    while directory/run identifiers control grouping.
    """

    return [
        f"/output/format {_normalize_output_format_token(config.metadata.output_info.output_format)}",
        f"/output/path {resolve_data_directory(config)}",
        f"/output/filename {DEFAULT_OUTPUT_FILENAME_BASE}",
        f"/output/runname {config.metadata.simulation_run_id}",
    ]


def _resolve_sensitive_detector_diameter_mm(config: SimConfig) -> float:
    """Resolve sensitive-detector diameter from configured rule expression.

    Supported rules intentionally mirror a constrained expression set rather
    than a general expression evaluator:
    - ``min(entranceDiameter,sensorMaxWidth)``
    - ``entranceDiameter``
    - ``sensorMaxWidth``
    """

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
    """Build Geant4 geometry command list from hierarchical config.

    Geometry mapping overview
    -------------------------
    - Scintillator dimensions/position map directly from ``scintillator`` block.
    - Scintillator material uses ``scintillator.properties.name``.
    - Aperture command is emitted only for circular detector shape.
      Aperture radius is half of the resolved detector diameter rule.
    - Optical-interface XY uses ``optical.geometry.entranceDiameter``.
    - Optical-interface Z thickness uses project default
      ``DEFAULT_OPTICAL_INTERFACE_THICKNESS_MM``.
    - Optical-interface position maps from
      ``optical.sensitiveDetectorConfig.position_mm``.
    """

    scint = config.scintillator
    optical = config.optical
    detector = optical.sensitive_detector_config

    # Base scintillator commands are always emitted.
    commands = [
        f"/scintillator/geom/material {scint.properties.name}",
        f"/scintillator/geom/scintX {scint.dimension_mm.x_mm:g} mm",
        f"/scintillator/geom/scintY {scint.dimension_mm.y_mm:g} mm",
        f"/scintillator/geom/scintZ {scint.dimension_mm.z_mm:g} mm",
        f"/scintillator/geom/posX {scint.position_mm.x_mm:g} mm",
        f"/scintillator/geom/posY {scint.position_mm.y_mm:g} mm",
        f"/scintillator/geom/posZ {scint.position_mm.z_mm:g} mm",
    ]

    # Circular detector shape implies an aperture mask command in this
    # simulation pipeline.
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

    # Stage directories are created explicitly from Python so runtime C++ IO can
    # assume parents already exist.
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
    """Build full macro command block in stable order.

    Ordering:
    1. Optional ``/output/*`` commands
    2. Geometry commands
    3. Optional ``/run/initialize``
    """

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
    """Write a Geant4 macro file from config.

    Parameters
    ----------
    config:
        Source validated simulation configuration.
    macro_path:
        Destination path. When ``None``, uses ``resolve_default_macro_path``.
    include_output:
        Include output configuration commands.
    include_run_initialize:
        Append ``/run/initialize`` at end of generated macro.
    create_output_directories:
        Create output/log/macro directories before writing.
    overwrite:
        Guard against accidental overwrite when ``False``.
    """

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
    """Append command lines to an existing macro file.

    This is primarily intended for script-level command tails (GPS setup,
    beamOn commands, visualization commands) that should follow the generated
    base block.
    """

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
