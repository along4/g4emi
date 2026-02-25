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
5. Write full macro files.

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
from typing import Any, Literal

try:
    from src.config.SimConfig import SimConfig, default_sim_config
    from src.config.ScintillatorCatalogIO import load_scintillator
    from src.config.utilsConfig import resolve_path
except ModuleNotFoundError:
    # Support imports when repository root is not already on sys.path.
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from src.config.SimConfig import SimConfig, default_sim_config
    from src.config.ScintillatorCatalogIO import load_scintillator
    from src.config.utilsConfig import resolve_path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - dependency availability varies
    yaml = None


SIMULATED_PHOTONS_STAGE_DIR = "simulatedPhotons"
TRANSPORT_PHOTONS_STAGE_DIR = "transportedPhotons"
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

_ENERGY_UNIT_TO_MEV: dict[str, float] = {
    "ev": 1.0e-6,
    "kev": 1.0e-3,
    "mev": 1.0,
    "gev": 1.0e3,
}

_ENERGY_UNIT_TO_EV: dict[str, float] = {
    "ev": 1.0,
    "kev": 1.0e3,
    "mev": 1.0e6,
    "gev": 1.0e9,
}

_TIME_UNIT_TO_NS: dict[str, float] = {
    "s": 1.0e9,
    "ms": 1.0e6,
    "us": 1.0e3,
    "ns": 1.0,
    "ps": 1.0e-3,
}

_DENSITY_UNIT_TO_G_CM3: dict[str, float] = {
    "g/cm3": 1.0,
    "g/cm^3": 1.0,
    "kg/m3": 1.0e-3,
    "kg/m^3": 1.0e-3,
}

_SCINT_YIELD_UNIT_TO_PER_MEV: dict[str, float] = {
    "1/mev": 1.0,
    "1/kev": 1.0e3,
    "1/gev": 1.0e-3,
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


def _parse_vector3(tokens: list[str], command: str) -> tuple[float, float, float]:
    """Parse three scalar tokens from a macro command."""

    if len(tokens) < 4:
        raise ValueError(
            f"Command '{command}' requires three scalar tokens, got: {tokens!r}"
        )
    try:
        return float(tokens[1]), float(tokens[2]), float(tokens[3])
    except ValueError as exc:
        raise ValueError(
            f"Command '{command}' requires numeric vector tokens, got: {tokens[1:4]!r}"
        ) from exc


def _parse_energy_to_mev(tokens: list[str], command: str) -> float:
    """Parse `<value> <unit>` energy tokens and convert to MeV."""

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
    factor = _ENERGY_UNIT_TO_MEV.get(tokens[2].strip().lower())
    if factor is None:
        raise ValueError(
            f"Command '{command}' has unsupported energy unit: {tokens[2]!r}."
        )
    return value * factor


def _parse_numeric_list_with_optional_unit(
    tokens: list[str],
    command: str,
) -> tuple[list[float], str | None]:
    """Parse list command payload into numeric values plus optional unit token."""

    if len(tokens) < 2:
        raise ValueError(
            f"Command '{command}' requires a numeric list payload, got: {tokens!r}"
        )

    unit: str | None = None
    payload_tokens = tokens[1:]
    if len(payload_tokens) >= 2:
        try:
            float(payload_tokens[-1])
        except ValueError:
            unit = payload_tokens[-1]
            payload_tokens = payload_tokens[:-1]

    if not payload_tokens:
        raise ValueError(f"Command '{command}' is missing numeric list values.")

    raw_payload = " ".join(payload_tokens).replace(",", " ")
    values: list[float] = []
    for piece in raw_payload.split():
        try:
            values.append(float(piece))
        except ValueError as exc:
            raise ValueError(
                f"Command '{command}' has non-numeric list token: {piece!r}"
            ) from exc

    if not values:
        raise ValueError(f"Command '{command}' is missing numeric list values.")

    return values, unit


def _parse_time_to_ns(tokens: list[str], command: str) -> float:
    """Parse `<value> <unit>` time tokens and convert to nanoseconds."""

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
    factor = _TIME_UNIT_TO_NS.get(tokens[2].strip().lower())
    if factor is None:
        raise ValueError(
            f"Command '{command}' has unsupported time unit: {tokens[2]!r}."
        )
    return value * factor


def _parse_density_to_g_cm3(tokens: list[str], command: str) -> float:
    """Parse `<value> <unit>` density tokens and convert to g/cm3."""

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
    factor = _DENSITY_UNIT_TO_G_CM3.get(tokens[2].strip().lower())
    if factor is None:
        raise ValueError(
            f"Command '{command}' has unsupported density unit: {tokens[2]!r}."
        )
    return value * factor


def _parse_scint_yield_to_per_mev(tokens: list[str], command: str) -> float:
    """Parse scintillation-yield command payload into photons/MeV."""

    if len(tokens) < 2:
        raise ValueError(
            f"Command '{command}' requires at least a value token, got: {tokens!r}"
        )
    try:
        value = float(tokens[1])
    except ValueError as exc:
        raise ValueError(
            f"Command '{command}' has non-numeric value token: {tokens[1]!r}"
        ) from exc

    if len(tokens) == 2:
        return value

    factor = _SCINT_YIELD_UNIT_TO_PER_MEV.get(tokens[2].strip().lower())
    if factor is None:
        raise ValueError(
            f"Command '{command}' has unsupported scintillation-yield unit: {tokens[2]!r}."
        )
    return value * factor


def source_commands(config: SimConfig) -> list[str]:
    """Build GEANT4 GPS command lines from strict `source.gps` configuration."""

    gps = config.source.gps
    position = gps.position
    angular = gps.angular
    energy = gps.energy

    commands = [
        f"/gps/particle {gps.particle}",
        f"/gps/pos/type {position.type}",
        f"/gps/pos/shape {position.shape}",
        (
            f"/gps/pos/centre {position.center_mm.x_mm:g} "
            f"{position.center_mm.y_mm:g} {position.center_mm.z_mm:g} mm"
        ),
        f"/gps/pos/radius {position.radius_mm:g} mm",
        f"/gps/ang/type {angular.type}",
        f"/gps/ang/rot1 {angular.rot1.x:g} {angular.rot1.y:g} {angular.rot1.z:g}",
        f"/gps/ang/rot2 {angular.rot2.x:g} {angular.rot2.y:g} {angular.rot2.z:g}",
        f"/gps/direction {angular.direction.x:g} {angular.direction.y:g} {angular.direction.z:g}",
        f"/gps/ene/type {energy.type}",
    ]

    if energy.type.strip().lower() == "mono":
        mono_mev = energy.mono_mev
        if mono_mev is None:
            raise ValueError(
                "`source.gps.energy.monoMeV` is required when `/gps/ene/type Mono`."
            )
        commands.append(f"/gps/ene/mono {mono_mev:g} MeV")

    return commands


def _default_import_template(macro_path: Path) -> SimConfig:
    """Return sensible baseline config used for macro-import gaps.

    Macro files do not encode every field required by hierarchical ``SimConfig``
    (for example rich metadata and full lens descriptors). This baseline
    provides valid defaults that are then selectively overwritten by parsed
    macro commands.
    """

    payload = default_sim_config().model_dump(mode="python")
    metadata = payload["metadata"]
    run_environment = metadata["run_environment"]
    output_info = run_environment["output_info"]

    metadata["author"] = "Macro Import"
    metadata["date"] = DateType.today().isoformat()
    metadata["version"] = "imported"
    metadata["description"] = f"Imported from macro: {macro_path.name}"
    run_environment["simulation_run_id"] = macro_path.stem
    run_environment["working_directory"] = "data"
    run_environment["macro_directory"] = "macros"
    run_environment["log_directory"] = "logs"
    output_info["simulated_photons_dir"] = SIMULATED_PHOTONS_STAGE_DIR
    output_info["transported_photons_dir"] = TRANSPORT_PHOTONS_STAGE_DIR
    output_info["output_format"] = "hdf5"

    # Macro files may omit `/run/beamOn` and runtime-control preamble commands.
    # Keep simulation block unset by default so import does not invent them.
    payload["simulation"] = None

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
    - Macros are lossy relative to ``SimConfig``. They do not encode full lens
      setup and metadata context, so those values come from ``template`` defaults.
    - ``/output/filename`` is currently ignored because filename base is fixed
      by this pipeline.
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
    run_environment = metadata["run_environment"]
    output_info = run_environment["output_info"]
    scintillator = payload["scintillator"]
    scint_properties = scintillator.get("properties")
    if not isinstance(scint_properties, dict):
        scint_properties = {}
        scintillator["properties"] = scint_properties
    optical = payload["optical"]
    geometry = optical["geometry"]
    detector = optical["sensitive_detector_config"]
    simulation = payload.get("simulation")
    source_gps = payload["source"]["gps"]
    position = source_gps["position"]
    angular = source_gps["angular"]
    energy = source_gps["energy"]
    runtime_controls = (
        simulation.get("runtime_controls")
        if isinstance(simulation, dict)
        else None
    )

    entrance_diameter_mm: float | None = None
    size_x_mm: float | None = None
    size_y_mm: float | None = None
    aperture_radius_mm: float | None = None
    parsed_thickness_mm: float | None = None
    parsed_output_path: str | None = None
    parsed_output_runname: str | None = None

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
            parsed_output_path = tokens[1]
            continue
        if command == "/output/runname" and len(tokens) >= 2:
            parsed_output_runname = tokens[1].strip()
            continue
        if command == "/control/verbose" and len(tokens) >= 2:
            if simulation is None:
                simulation = {}
                payload["simulation"] = simulation
            if runtime_controls is None:
                runtime_controls = {}
                simulation["runtime_controls"] = runtime_controls
            runtime_controls["control_verbose"] = int(tokens[1])
            continue
        if command == "/run/verbose" and len(tokens) >= 2:
            if simulation is None:
                simulation = {}
                payload["simulation"] = simulation
            if runtime_controls is None:
                runtime_controls = {}
                simulation["runtime_controls"] = runtime_controls
            runtime_controls["run_verbose"] = int(tokens[1])
            continue
        if command == "/event/verbose" and len(tokens) >= 2:
            if simulation is None:
                simulation = {}
                payload["simulation"] = simulation
            if runtime_controls is None:
                runtime_controls = {}
                simulation["runtime_controls"] = runtime_controls
            runtime_controls["event_verbose"] = int(tokens[1])
            continue
        if command == "/tracking/verbose" and len(tokens) >= 2:
            if simulation is None:
                simulation = {}
                payload["simulation"] = simulation
            if runtime_controls is None:
                runtime_controls = {}
                simulation["runtime_controls"] = runtime_controls
            runtime_controls["tracking_verbose"] = int(tokens[1])
            continue
        if command == "/run/printProgress" and len(tokens) >= 2:
            if simulation is None:
                simulation = {}
                payload["simulation"] = simulation
            if runtime_controls is None:
                runtime_controls = {}
                simulation["runtime_controls"] = runtime_controls
            runtime_controls["print_progress"] = int(tokens[1])
            continue
        if command == "/tracking/storeTrajectory" and len(tokens) >= 2:
            raw = tokens[1].strip().lower()
            if raw in {"1", "true", "yes", "on"}:
                parsed_store = True
            elif raw in {"0", "false", "no", "off"}:
                parsed_store = False
            else:
                raise ValueError(
                    "Command '/tracking/storeTrajectory' requires boolean-like token "
                    f"(0/1/true/false), got: {tokens[1]!r}"
                )
            if simulation is None:
                simulation = {}
                payload["simulation"] = simulation
            if runtime_controls is None:
                runtime_controls = {}
                simulation["runtime_controls"] = runtime_controls
            runtime_controls["store_trajectory"] = parsed_store
            continue
        if command == "/run/beamOn" and len(tokens) >= 2:
            try:
                particle_count = int(tokens[1])
            except ValueError as exc:
                raise ValueError(
                    f"Command '{command}' requires integer particle count, got: {tokens[1]!r}"
                ) from exc
            if particle_count <= 0:
                raise ValueError(
                    f"Command '{command}' requires positive particle count, got: {particle_count}"
                )
            if simulation is None:
                simulation = {}
                payload["simulation"] = simulation
            simulation["number_of_particles"] = particle_count
            continue

        if command == "/gps/particle" and len(tokens) >= 2:
            source_gps["particle"] = tokens[1]
            continue
        if command == "/gps/pos/type" and len(tokens) >= 2:
            position["type"] = tokens[1]
            continue
        if command == "/gps/pos/shape" and len(tokens) >= 2:
            position["shape"] = tokens[1]
            continue
        if command == "/gps/pos/centre":
            if len(tokens) < 5:
                raise ValueError(
                    f"Command '{command}' requires '<x> <y> <z> <unit>', got: {tokens!r}"
                )
            x_mm = _length_to_mm(float(tokens[1]), tokens[4])
            y_mm = _length_to_mm(float(tokens[2]), tokens[4])
            z_mm = _length_to_mm(float(tokens[3]), tokens[4])
            position["center_mm"] = {"x_mm": x_mm, "y_mm": y_mm, "z_mm": z_mm}
            continue
        if command == "/gps/pos/radius":
            radius_mm = _parse_length_tokens(tokens, command)
            position["radius_mm"] = radius_mm
            continue
        if command == "/gps/ang/type" and len(tokens) >= 2:
            angular["type"] = tokens[1]
            continue
        if command == "/gps/ang/rot1":
            x, y, z = _parse_vector3(tokens, command)
            angular["rot1"] = {"x": x, "y": y, "z": z}
            continue
        if command == "/gps/ang/rot2":
            x, y, z = _parse_vector3(tokens, command)
            angular["rot2"] = {"x": x, "y": y, "z": z}
            continue
        if command == "/gps/direction":
            x, y, z = _parse_vector3(tokens, command)
            angular["direction"] = {"x": x, "y": y, "z": z}
            continue
        if command == "/gps/ene/type" and len(tokens) >= 2:
            energy["type"] = tokens[1]
            if tokens[1].strip().lower() != "mono":
                energy.pop("mono_mev", None)
            continue
        if command == "/gps/ene/mono":
            mono_mev = _parse_energy_to_mev(tokens, command)
            energy["mono_mev"] = mono_mev
            energy["type"] = "Mono"
            continue

        if command == "/scintillator/geom/material" and len(tokens) >= 2:
            scint_properties["name"] = tokens[1]
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
        if command == "/scintillator/properties/density":
            scint_properties["density"] = _parse_density_to_g_cm3(tokens, command)
            continue
        if command == "/scintillator/properties/carbonAtoms" and len(tokens) >= 2:
            scint_properties["carbon_atoms"] = int(tokens[1])
            continue
        if command == "/scintillator/properties/hydrogenAtoms" and len(tokens) >= 2:
            scint_properties["hydrogen_atoms"] = int(tokens[1])
            continue
        if command == "/scintillator/properties/photonEnergy":
            values, unit = _parse_numeric_list_with_optional_unit(tokens, command)
            factor = _ENERGY_UNIT_TO_EV.get((unit or "eV").strip().lower())
            if factor is None:
                raise ValueError(
                    f"Command '{command}' has unsupported energy unit: {unit!r}."
                )
            scint_properties["photon_energy"] = [value * factor for value in values]
            scint_properties["n_k_entries"] = len(values)
            continue
        if command == "/scintillator/properties/rIndex":
            values, unit = _parse_numeric_list_with_optional_unit(tokens, command)
            if unit is not None and unit.strip().lower() not in {"unitless", "none"}:
                raise ValueError(
                    f"Command '{command}' does not support unit token {unit!r}."
                )
            scint_properties["r_index"] = values
            if "n_k_entries" not in scint_properties:
                scint_properties["n_k_entries"] = len(values)
            continue
        if command == "/scintillator/properties/absLength":
            values, unit = _parse_numeric_list_with_optional_unit(tokens, command)
            factor = _LENGTH_UNIT_TO_MM.get((unit or "cm").strip().lower())
            if factor is None:
                raise ValueError(
                    f"Command '{command}' has unsupported length unit: {unit!r}."
                )
            scint_properties["abs_length"] = [(value * factor) / 10.0 for value in values]
            continue
        if command == "/scintillator/properties/scintSpectrum":
            values, unit = _parse_numeric_list_with_optional_unit(tokens, command)
            if unit is not None and unit.strip().lower() not in {"unitless", "none"}:
                raise ValueError(
                    f"Command '{command}' does not support unit token {unit!r}."
                )
            scint_properties["scint_spectrum"] = values
            continue
        if command == "/scintillator/properties/scintYield":
            scint_properties["scint_yield"] = _parse_scint_yield_to_per_mev(
                tokens, command
            )
            continue
        if command == "/scintillator/properties/resolutionScale" and len(tokens) >= 2:
            scint_properties["resolution_scale"] = float(tokens[1])
            continue
        if command == "/scintillator/properties/timeConstant":
            scint_properties["time_constant"] = _parse_time_to_ns(tokens, command)
            continue
        if command == "/scintillator/properties/yield1" and len(tokens) >= 2:
            scint_properties["yield1"] = float(tokens[1])
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

    # Ensure required GPS fields remain valid if a macro omits specific commands.
    position.setdefault("type", "Plane")
    position.setdefault("shape", "Circle")
    energy.setdefault("type", "Mono")
    if energy.get("type", "").strip().lower() == "mono":
        energy.setdefault("mono_mev", 1.0)

    # Consolidate Geant4 output commands into run-environment layout.
    # /output/path <base>     -> WorkingDirectory=<base>
    # /output/runname <id>    -> SimulationRunID=<id>
    if parsed_output_runname is not None and parsed_output_runname.strip():
        run_environment["simulation_run_id"] = parsed_output_runname.strip()
    if parsed_output_path is not None:
        run_environment["working_directory"] = str(Path(parsed_output_path))

    return SimConfig.model_validate(payload)


def _extract_sim_config_payload(parsed: dict[str, Any]) -> dict[str, Any]:
    """Extract top-level keys recognized by `SimConfig`.

    This intentionally allows script-level extras to coexist in one YAML file.
    """

    # `SimConfig` accepts "metadata" field name internally while user YAML may
    # use aliased "Metadata". Keep both accepted at top-level extraction time.
    accepted_keys = set(SimConfig.model_fields.keys()) | {"Metadata"}
    return {key: value for key, value in parsed.items() if key in accepted_keys}


def _catalog_properties_payload(catalog_id: str) -> dict[str, Any]:
    """Resolve baseline `scintillator.properties` payload from catalog id."""

    loaded = load_scintillator(catalog_id)
    energy_unit = loaded.r_index.x_unit.strip().lower()
    energy_factor = _ENERGY_UNIT_TO_EV.get(energy_unit)
    if energy_factor is None:
        raise ValueError(
            f"Catalog scintillator '{catalog_id}' uses unsupported energy unit "
            f"{loaded.r_index.x_unit!r}; supported: eV, keV, MeV, GeV."
        )
    photon_energy = [value * energy_factor for value in loaded.r_index.energy]

    abs_unit = loaded.abs_length.y_unit.strip().lower()
    abs_factor = _LENGTH_UNIT_TO_MM.get(abs_unit)
    if abs_factor is None:
        raise ValueError(
            f"Catalog scintillator '{catalog_id}' uses unsupported absLength unit "
            f"{loaded.abs_length.y_unit!r}."
        )
    abs_length_cm = [(value * abs_factor) / 10.0 for value in loaded.abs_length.value]

    time_unit = loaded.material.optical.constants.time_constant.unit.strip().lower()
    time_factor = _TIME_UNIT_TO_NS.get(time_unit)
    if time_factor is None:
        raise ValueError(
            f"Catalog scintillator '{catalog_id}' uses unsupported time unit "
            f"{loaded.material.optical.constants.time_constant.unit!r}."
        )
    time_constant_ns = loaded.material.optical.constants.time_constant.value * time_factor

    density_unit = loaded.material.composition.density.unit.strip().lower()
    density_factor = _DENSITY_UNIT_TO_G_CM3.get(density_unit)
    if density_factor is None:
        raise ValueError(
            f"Catalog scintillator '{catalog_id}' uses unsupported density unit "
            f"{loaded.material.composition.density.unit!r}."
        )
    density_g_cm3 = loaded.material.composition.density.value * density_factor

    yield_unit = loaded.material.optical.constants.scint_yield.unit.strip().lower()
    yield_factor = _SCINT_YIELD_UNIT_TO_PER_MEV.get(yield_unit)
    if yield_factor is None:
        raise ValueError(
            f"Catalog scintillator '{catalog_id}' uses unsupported scintYield unit "
            f"{loaded.material.optical.constants.scint_yield.unit!r}."
        )
    scint_yield_per_mev = loaded.material.optical.constants.scint_yield.value * yield_factor

    payload: dict[str, Any] = {
        "name": loaded.material.id,
        "photonEnergy": photon_energy,
        "rIndex": list(loaded.r_index.value),
        "absLength": abs_length_cm,
        "scintSpectrum": list(loaded.scint_spectrum.value),
        "nKEntries": len(photon_energy),
        "timeConstant": time_constant_ns,
        "density": density_g_cm3,
        "scintYield": scint_yield_per_mev,
        "resolutionScale": loaded.material.optical.constants.resolution_scale,
        "yield1": loaded.material.optical.constants.yield1,
    }
    carbon_atoms = loaded.material.composition.atoms.get("C")
    hydrogen_atoms = loaded.material.composition.atoms.get("H")
    if carbon_atoms is not None:
        payload["carbonAtoms"] = carbon_atoms
    if hydrogen_atoms is not None:
        payload["hydrogenAtoms"] = hydrogen_atoms
    return payload


def _apply_scintillator_catalog_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    """Hydrate `scintillator.properties` from catalog defaults when requested."""

    scintillator = payload.get("scintillator")
    if not isinstance(scintillator, dict):
        return payload

    catalog_id = scintillator.get("catalogId", scintillator.get("catalog_id"))
    if catalog_id is None:
        return payload
    if not isinstance(catalog_id, str) or not catalog_id.strip():
        raise ValueError("`scintillator.catalogId` must be a non-empty string.")

    catalog_props = _catalog_properties_payload(catalog_id.strip())

    raw_properties = scintillator.get("properties")
    if raw_properties is None:
        merged_properties: dict[str, Any] = {}
    elif isinstance(raw_properties, dict):
        merged_properties = dict(raw_properties)
    else:
        raise ValueError("`scintillator.properties` must be a mapping/object.")

    # Explicit YAML values win; catalog fills missing keys.
    for key, value in catalog_props.items():
        merged_properties.setdefault(key, value)

    scintillator["properties"] = merged_properties
    return payload


def from_yaml(yaml_path: str | Path) -> SimConfig:
    """Load and validate a :class:`SimConfig` from YAML file.

    Extra top-level keys are ignored so callers can keep script-level settings
    in the same YAML file.

    This behavior is intentional for example workflows where a single YAML file
    carries both strict simulation config and script orchestration values (such
    as optional script output-path overrides).
    """

    parsed = load_yaml_mapping(yaml_path)
    payload = _extract_sim_config_payload(parsed)
    payload = _apply_scintillator_catalog_defaults(payload)
    return SimConfig.model_validate(payload)


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
      ``Metadata``, ``RunEnvironment``, and camelCase optical/scintillator keys.
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
    """Resolve ``Metadata.RunEnvironment.WorkingDirectory`` into absolute form."""

    return resolve_path(config.metadata.run_environment.working_directory)


def _run_root(config: SimConfig) -> Path:
    """Resolve run root directory as `<WorkingDirectory>/<SimulationRunID>`."""

    run_id = config.metadata.run_environment.simulation_run_id.strip()
    if not run_id:
        return _working_directory(config)
    return (_working_directory(config) / run_id).resolve()


def resolve_run_environment_directory(
    config: SimConfig,
    target: Literal[
        "data",
        "run_root",
        "macro",
        "log",
        "simulated_photons",
        "transported_photons",
    ],
) -> Path:
    """Resolve a run-environment directory by semantic target token.

    Supported targets:
    - ``data``: ``RunEnvironment.WorkingDirectory``
    - ``run_root``: ``<WorkingDirectory>/<SimulationRunID>``
    - ``macro``: ``<run_root>/<MacroDirectory>``
    - ``log``: ``<run_root>/<LogDirectory>``
    - ``simulated_photons``: ``<run_root>/<SimulatedPhotonsDirectory>``
    - ``transported_photons``: ``<run_root>/<TransportedPhotonsDirectory>``
    """

    if target == "data":
        return _working_directory(config)
    if target == "run_root":
        return _run_root(config)

    env = config.metadata.run_environment
    target_directory: dict[str, str] = {
        "macro": env.macro_directory,
        "log": env.log_directory,
        "simulated_photons": env.output_info.simulated_photons_dir,
        "transported_photons": env.output_info.transported_photons_dir,
    }
    resolved = target_directory.get(target)
    if resolved is None:
        raise ValueError(
            "Unsupported run-environment target. "
            "Expected one of: data, run_root, macro, log, "
            "simulated_photons, transported_photons."
        )
    return resolve_path(resolved, base_directory=_run_root(config))


def resolve_default_macro_path(config: SimConfig) -> Path:
    """Resolve default macro output path for ``write_macro(..., macro_path=None)``.

    File naming policy:
    - ``<SimulationRunID>.mac`` when run id is non-empty
    - ``generated_from_config.mac`` otherwise
    """

    run_name = config.metadata.run_environment.simulation_run_id.strip()
    macro_filename = (
        f"{run_name}.mac" if run_name else DEFAULT_GENERATED_MACRO_FILENAME
    )
    return (
        resolve_run_environment_directory(config, "macro") / macro_filename
    ).resolve()


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
    - ``RunEnvironment.OutputInfo.OutputFormat`` -> ``/output/format``
    - ``RunEnvironment.WorkingDirectory``            -> ``/output/path``
    - fixed base filename                          -> ``/output/filename``
    - ``RunEnvironment.SimulationRunID``          -> ``/output/runname``

    The filename base is fixed so simulation artifacts remain consistently named
    while directory/run identifiers control grouping.
    """

    return [
        f"/output/format {_normalize_output_format_token(config.metadata.run_environment.output_info.output_format)}",
        f"/output/path {resolve_run_environment_directory(config, 'data')}",
        f"/output/filename {DEFAULT_OUTPUT_FILENAME_BASE}",
        f"/output/runname {config.metadata.run_environment.simulation_run_id}",
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


def _format_float_list(values: list[float]) -> str:
    """Format list values for compact macro list payloads."""

    return ",".join(f"{value:g}" for value in values)


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
    if scint.properties is None:
        raise ValueError(
            "`scintillator.properties` is missing. "
            "Load config via `from_yaml(...)` with `catalogId` or provide explicit properties."
        )

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

    # Extended scintillator material/optical properties are emitted when present.
    if scint.properties.density is not None:
        commands.append(
            f"/scintillator/properties/density {scint.properties.density:g} g/cm3"
        )
    if scint.properties.carbon_atoms is not None:
        commands.append(
            f"/scintillator/properties/carbonAtoms {scint.properties.carbon_atoms}"
        )
    if scint.properties.hydrogen_atoms is not None:
        commands.append(
            f"/scintillator/properties/hydrogenAtoms {scint.properties.hydrogen_atoms}"
        )
    commands.append(
        "/scintillator/properties/photonEnergy "
        f"{_format_float_list(scint.properties.photon_energy)} eV"
    )
    commands.append(
        "/scintillator/properties/rIndex "
        f"{_format_float_list(scint.properties.r_index)}"
    )
    if scint.properties.abs_length is not None:
        commands.append(
            "/scintillator/properties/absLength "
            f"{_format_float_list(scint.properties.abs_length)} cm"
        )
    if scint.properties.scint_spectrum is not None:
        commands.append(
            "/scintillator/properties/scintSpectrum "
            f"{_format_float_list(scint.properties.scint_spectrum)}"
        )
    if scint.properties.scint_yield is not None:
        commands.append(
            f"/scintillator/properties/scintYield {scint.properties.scint_yield:g}"
        )
    if scint.properties.resolution_scale is not None:
        commands.append(
            "/scintillator/properties/resolutionScale "
            f"{scint.properties.resolution_scale:g}"
        )
    commands.append(
        f"/scintillator/properties/timeConstant {scint.properties.time_constant:g} ns"
    )
    if scint.properties.yield1 is not None:
        commands.append(f"/scintillator/properties/yield1 {scint.properties.yield1:g}")

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
    - output stage from `RunEnvironment.OutputInfo.SimulatedPhotonsDirectory`
    - transport stage from `RunEnvironment.OutputInfo.TransportedPhotonsDirectory`
    - log directory from `RunEnvironment.LogDirectory`
    """

    # Stage directories are created explicitly from Python so runtime C++ IO can
    # assume parents already exist.
    output_stage_dir = resolve_run_environment_directory(config, "simulated_photons")
    output_stage_dir.mkdir(parents=True, exist_ok=True)

    transport_stage_dir = resolve_run_environment_directory(
        config, "transported_photons"
    )
    transport_stage_dir.mkdir(parents=True, exist_ok=True)

    log_dir = resolve_run_environment_directory(config, "log")
    log_dir.mkdir(parents=True, exist_ok=True)

    return output_stage_dir


def ensure_macro_directories(config: SimConfig) -> Path:
    """Create and return the macros stage directory for this config."""

    macro_stage_dir = resolve_run_environment_directory(config, "macro")
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
    1. Optional ``simulation.runtimeControls`` preamble commands
    2. Optional ``/output/*`` commands
    3. Geometry commands
    4. Optional ``/run/initialize``
    5. Source (GPS) commands
    6. Optional ``/run/beamOn <N>`` from ``simulation.numberOfParticles``
    """

    commands: list[str] = []
    if config.simulation is not None and config.simulation.runtime_controls is not None:
        runtime = config.simulation.runtime_controls
        if runtime.control_verbose is not None:
            commands.append(f"/control/verbose {runtime.control_verbose}")
        if runtime.run_verbose is not None:
            commands.append(f"/run/verbose {runtime.run_verbose}")
        if runtime.event_verbose is not None:
            commands.append(f"/event/verbose {runtime.event_verbose}")
        if runtime.tracking_verbose is not None:
            commands.append(f"/tracking/verbose {runtime.tracking_verbose}")
        if runtime.print_progress is not None:
            commands.append(f"/run/printProgress {runtime.print_progress}")
        if runtime.store_trajectory is not None:
            commands.append(
                f"/tracking/storeTrajectory {1 if runtime.store_trajectory else 0}"
            )
    if include_output:
        commands.extend(output_commands(config))
    commands.extend(geometry_commands(config))
    if include_run_initialize:
        commands.append("/run/initialize")
    commands.extend(source_commands(config))
    if (
        config.simulation is not None
        and config.simulation.number_of_particles is not None
    ):
        commands.append(f"/run/beamOn {config.simulation.number_of_particles}")
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
