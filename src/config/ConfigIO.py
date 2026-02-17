"""Macro-file load/save helpers for :mod:`src.config.SimConfig`.

This module intentionally owns all macro I/O responsibilities so
`SimConfig` can stay focused on:
- geometry/lens validation
- deterministic command generation from a validated model

The public API mirrors the practical workflow used in simulation scripts:
1. Load an existing macro into a `SimConfig` (`from_macro`).
2. Generate macro command blocks (`output_commands`, `macro_commands`).
3. Create directory roots (`ensure_directory`).
4. Prepare stage output directories (`ensure_output_directories`).
5. Read raw YAML mappings (`load_yaml_mapping`) and validated config
   (`from_yaml`).
6. Write configuration YAML (`write_yaml`).
7. Write a full macro from scratch (`write_macro`).
8. Patch only geometry lines in-place in an existing macro
   (`apply_geometry_to_macro`).
"""

from __future__ import annotations

import math
from pathlib import Path
import sys
from typing import Any

try:
    from src.config.SimConfig import SimConfig
except ModuleNotFoundError:
    # Support imports when repository root is not already on sys.path.
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from src.config.SimConfig import SimConfig

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - dependency availability varies
    yaml = None


# Stage folders used under the effective run root.
SIMULATED_PHOTONS_STAGE_DIR = "simulatedPhotons"
TRANSPORT_PHOTONS_STAGE_DIR = "transportPhotons"
MACROS_STAGE_DIR = "macros"
DEFAULT_GENERATED_MACRO_FILENAME = "generated_from_config.mac"

# Geant4-style length unit conversion table (values converted to mm).
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


def _length_to_mm(value: float, unit: str) -> float:
    """Convert a numeric value in Geant4-style units to millimeters.

    Parameters
    ----------
    value:
        Numeric magnitude from a macro command token.
    unit:
        Unit token from the macro command (for example `mm`, `cm`, `m`).

    Returns
    -------
    float
        Converted value in millimeters.

    Raises
    ------
    ValueError
        If the unit token is not recognized.
    """

    factor = _LENGTH_UNIT_TO_MM.get(unit.strip().lower())
    if factor is None:
        raise ValueError(f"Unsupported length unit '{unit}'.")
    return value * factor


def _parse_length_tokens(tokens: list[str], command: str) -> float:
    """Parse a macro command value/unit pair and return millimeters.

    Expected token structure is:
    `['/path/to/command', '<value>', '<unit>', ...]`

    Additional trailing tokens are ignored because this helper is used only
    with fixed-format geometry commands where the first three tokens carry the
    full scalar payload.
    """

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


def _unquote_token(token: str) -> str:
    """Strip one matching quote layer from a macro string token."""

    if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
        return token[1:-1]
    return token


def _require_yaml_dependency() -> Any:
    """Return PyYAML module or raise a clear dependency error.

    YAML functionality is optional at import time; we only require the
    dependency when YAML-specific helpers are called.
    """

    if yaml is None:
        raise ModuleNotFoundError(
            "PyYAML is required for YAML config IO. "
            "Install it in your environment (for example: pixi add pyyaml)."
        )
    return yaml


def from_macro(
    macro_path: str | Path,
    *,
    lenses: list[str] | None = None,
    reversed: bool | list[bool] = False,
) -> SimConfig:
    """Build a :class:`SimConfig` by reading geometry/output lines from a macro.

    Notes
    -----
    - Lens selection/orientation is not encoded in Geant4 macro files, so this
      function accepts `lenses` and `reversed` as explicit parameters.
    - Unknown commands are ignored.
    - The optical-interface diameter field is inferred from
      `/optical_interface/geom/sizeX` and `/optical_interface/geom/sizeY`.
      If both are present and differ, a `ValueError` is raised.
    - If `/optical_interface/geom/posZ` is present, the standoff
      (`scint_back_to_optical_interface_mm`) is derived from the parsed
      scintillator geometry and interface thickness.
    """

    path = Path(macro_path)
    if not path.exists():
        raise FileNotFoundError(f"Macro file not found: {path}")

    # Parse into an update dictionary in SimConfig-native field units.
    # SimConfig stores mixed units by field:
    # - *_cm fields in centimeters
    # - *_mm fields in millimeters
    updates: dict[str, object] = {}

    size_x_mm: float | None = None
    size_y_mm: float | None = None
    optical_interface_pos_z_mm: float | None = None
    aperture_seen = False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        tokens = line.split()
        command = tokens[0]

        if command == "/output/format" and len(tokens) >= 2:
            updates["output_format"] = tokens[1]
            continue
        if command == "/output/path" and len(tokens) >= 2:
            parsed = _unquote_token(tokens[1])
            updates["output_path"] = parsed or None
            continue
        if command == "/output/filename" and len(tokens) >= 2:
            updates["output_filename"] = _unquote_token(tokens[1])
            continue
        if command == "/output/runname" and len(tokens) >= 2:
            updates["output_runname"] = _unquote_token(tokens[1])
            continue

        if command == "/scintillator/geom/material" and len(tokens) >= 2:
            updates["scint_material"] = tokens[1]
            continue
        if command == "/scintillator/geom/scintX":
            updates["scint_x_cm"] = _parse_length_tokens(tokens, command) / 10.0
            continue
        if command == "/scintillator/geom/scintY":
            updates["scint_y_cm"] = _parse_length_tokens(tokens, command) / 10.0
            continue
        if command == "/scintillator/geom/scintZ":
            updates["scint_z_cm"] = _parse_length_tokens(tokens, command) / 10.0
            continue
        if command == "/scintillator/geom/posX":
            updates["scint_pos_x_cm"] = _parse_length_tokens(tokens, command) / 10.0
            continue
        if command == "/scintillator/geom/posY":
            updates["scint_pos_y_cm"] = _parse_length_tokens(tokens, command) / 10.0
            continue
        if command == "/scintillator/geom/posZ":
            updates["scint_pos_z_cm"] = _parse_length_tokens(tokens, command) / 10.0
            continue
        if command == "/scintillator/geom/apertureRadius":
            updates["aperture_radius_mm"] = _parse_length_tokens(tokens, command)
            aperture_seen = True
            continue

        if command == "/optical_interface/geom/sizeX":
            size_x_mm = _parse_length_tokens(tokens, command)
            continue
        if command == "/optical_interface/geom/sizeY":
            size_y_mm = _parse_length_tokens(tokens, command)
            continue
        if command == "/optical_interface/geom/thickness":
            updates["optical_interface_thickness_mm"] = _parse_length_tokens(
                tokens, command
            )
            continue
        if command == "/optical_interface/geom/posX":
            updates["optical_interface_pos_x_cm"] = (
                _parse_length_tokens(tokens, command) / 10.0
            )
            continue
        if command == "/optical_interface/geom/posY":
            updates["optical_interface_pos_y_cm"] = (
                _parse_length_tokens(tokens, command) / 10.0
            )
            continue
        if command == "/optical_interface/geom/posZ":
            optical_interface_pos_z_mm = _parse_length_tokens(tokens, command)
            continue

    if aperture_seen:
        updates["use_aperture_mask"] = True
    else:
        # Missing aperture command in macro means no explicit mask.
        # This avoids silently inventing a mask on load.
        updates["use_aperture_mask"] = False
        updates["aperture_radius_mm"] = None

    if size_x_mm is not None and size_y_mm is not None:
        if not math.isclose(size_x_mm, size_y_mm, rel_tol=0.0, abs_tol=1.0e-9):
            raise ValueError(
                "Loaded macro has non-circular optical-interface size: "
                f"sizeX={size_x_mm:.6f} mm, sizeY={size_y_mm:.6f} mm."
            )
        updates["optical_interface_diameter_mm"] = size_x_mm
    elif size_x_mm is not None:
        updates["optical_interface_diameter_mm"] = size_x_mm
    elif size_y_mm is not None:
        updates["optical_interface_diameter_mm"] = size_y_mm

    if optical_interface_pos_z_mm is not None:
        # Derive requested standoff from absolute optical-interface center Z:
        # standoff = front_face_z - scint_back_face_z
        #          = (center_z - thickness/2) - (scint_center + scint_thickness/2)
        scint_pos_z_cm = float(updates.get("scint_pos_z_cm", 0.0))
        scint_z_cm = float(updates.get("scint_z_cm", 2.0))
        optical_interface_thickness_mm = float(
            updates.get("optical_interface_thickness_mm", 0.1)
        )
        scint_back_face_z_mm = (scint_pos_z_cm * 10.0) + (0.5 * scint_z_cm * 10.0)
        optical_interface_front_face_z_mm = (
            optical_interface_pos_z_mm - 0.5 * optical_interface_thickness_mm
        )
        updates["scint_back_to_optical_interface_mm"] = (
            optical_interface_front_face_z_mm - scint_back_face_z_mm
        )

    effective_lenses = ["canon50"] if lenses is None else lenses
    return SimConfig(lenses=effective_lenses, reversed=reversed, **updates)


def from_yaml(yaml_path: str | Path) -> SimConfig:
    """Load a :class:`SimConfig` from a YAML file.

    Expected YAML shape:
    - top-level mapping where keys correspond to `SimConfig` fields.

    Validation behavior:
    - Fails if file is missing.
    - Parses with `yaml.safe_load`.
    - Validates through `SimConfig.model_validate(...)`.
    """

    parsed = load_yaml_mapping(yaml_path)
    return SimConfig.model_validate(parsed)


def load_yaml_mapping(yaml_path: str | Path) -> dict[str, Any]:
    """Load and validate a top-level YAML mapping/object.

    This helper is intentionally unopinionated about keys so callers can
    combine strict `SimConfig` fields with script-level settings in one file.
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


def write_yaml(
    config: SimConfig,
    yaml_path: str | Path,
    *,
    include_derived: bool = False,
    overwrite: bool = True,
) -> None:
    """Write a :class:`SimConfig` to a YAML file.

    Parameters
    ----------
    config:
        Source simulation configuration.
    yaml_path:
        Destination YAML file path.
    include_derived:
        When `False`, write only direct model fields.
        When `True`, include derived lens/geometry summary via `to_dict()`.
    overwrite:
        If `False`, raise `FileExistsError` when destination already exists.
    """

    module_yaml = _require_yaml_dependency()
    path = Path(yaml_path)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")

    payload: dict[str, Any]
    if include_derived:
        payload = config.to_dict()
    else:
        payload = config.model_dump(mode="python")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        module_yaml.safe_dump(payload, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _repo_root() -> Path:
    """Return repository root inferred from this module location."""

    return Path(__file__).resolve().parents[2]


def ensure_directory(path: str | Path) -> Path:
    """Create a directory path (including parents) and return its resolved Path."""

    directory = Path(path).expanduser()
    if not directory.is_absolute():
        directory = _repo_root() / directory
    directory.mkdir(parents=True, exist_ok=True)
    return directory.resolve()


def resolve_optional_path(
    value: Any,
    *,
    key_name: str,
    base_directory: str | Path | None = None,
) -> Path | None:
    """Resolve an optional YAML path-like value into an absolute path.

    Validation behavior:
    - `None` or blank string -> `None`
    - non-string non-null -> `ValueError`
    - relative string -> resolved against `base_directory` (or repo root)
    """

    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"YAML key `{key_name}` must be a string when provided.")
    if not value.strip():
        return None

    path = Path(value).expanduser()
    if not path.is_absolute():
        if base_directory is None:
            base = _repo_root()
        else:
            base = Path(base_directory).expanduser()
            if not base.is_absolute():
                base = _repo_root() / base
        path = base / path
    return path.resolve()


def _strip_known_output_extension(filename: str) -> str:
    """Strip known output extensions so callers can pass base-or-full filenames."""

    suffix = Path(filename).suffix.lower()
    if suffix in {".csv", ".h5", ".hdf5"}:
        return str(Path(filename).with_suffix(""))
    return filename


def _effective_output_root(config: SimConfig) -> Path:
    """Return effective output root directory with fallback-to-`data`.

    Fallback policy:
    - If `output_path` is missing/blank -> `<repo>/data`
    - If `output_path` resolves to an existing directory -> use it
    - Otherwise -> `<repo>/data`
    """

    default_root = _repo_root() / "data"
    raw_path = config.output_path
    if raw_path is None or not str(raw_path).strip():
        return default_root

    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = _repo_root() / candidate

    try:
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()
    except OSError:
        pass
    return default_root


def _effective_output_path_command_value(config: SimConfig) -> str:
    """Return macro `/output/path` value with fallback-to-`data` semantics."""

    root = _effective_output_root(config)
    default_root = (_repo_root() / "data").resolve()
    if root == default_root:
        return "data"
    return str(root)


def _effective_run_root(config: SimConfig) -> Path:
    """Resolve effective root directory shared by stage subdirectories.

    This root is the parent directory under which stage folders (for example
    `simulatedPhotons/`, `transportPhotons/`, and `macros/`) are created.
    """

    run_name = (config.output_runname or "").strip()
    base = _effective_output_root(config)
    if run_name:
        return (base / run_name).resolve()

    # When runname is absent and output_path falls back to data, preserve
    # output_filename-parent behavior so non-runname legacy paths stay usable.
    if base == (_repo_root() / "data").resolve() and (
        config.output_path is None or not str(config.output_path).strip()
    ):
        filename_path = Path(_strip_known_output_extension(config.output_filename))
        filename_parent = filename_path.parent
        if filename_parent == Path("."):
            base = _repo_root() / "data"
        else:
            base = filename_parent
            if not base.is_absolute():
                base = _repo_root() / base
        return base.resolve()

    return base.resolve()


def resolve_output_stage_directory(config: SimConfig) -> Path:
    """Resolve the final stage directory for simulation output files."""

    return (_effective_run_root(config) / SIMULATED_PHOTONS_STAGE_DIR).resolve()


def resolve_transport_photons_stage_directory(config: SimConfig) -> Path:
    """Resolve the transport-photons stage directory under the run root."""

    return (_effective_run_root(config) / TRANSPORT_PHOTONS_STAGE_DIR).resolve()


def resolve_macro_stage_directory(config: SimConfig) -> Path:
    """Resolve the macros stage directory sibling to `simulatedPhotons`."""

    return (_effective_run_root(config) / MACROS_STAGE_DIR).resolve()


def resolve_default_macro_path(config: SimConfig) -> Path:
    """Resolve default macro output path for `write_macro(..., macro_path=None)`.

    Default filename policy:
    - use `<runname>.mac` when runname is non-empty
    - otherwise use `generated_from_config.mac`
    """

    run_name = (config.output_runname or "").strip()
    macro_filename = (
        f"{run_name}.mac" if run_name else DEFAULT_GENERATED_MACRO_FILENAME
    )
    return (resolve_macro_stage_directory(config) / macro_filename).resolve()


def output_commands(config: SimConfig) -> list[str]:
    """Return output control command lines for a validated config.

    Output-path behavior:
    - If configured output_path is missing/unresolvable, emits `/output/path data`
      so runtime output routing falls back to repository `data/`.
    """

    commands = [
        f"/output/format {config.output_format}",
        f"/output/path {_effective_output_path_command_value(config)}",
        f"/output/filename {config.output_filename}",
        f"/output/runname {config.output_runname}",
    ]
    return commands


def ensure_output_directories(config: SimConfig) -> Path:
    """Create and return the simulation output stage directory.

    This helper is the intended Python-side directory creation entrypoint.
    It creates both:
    - `simulatedPhotons/` (current Geant4 output target)
    - `transportPhotons/` (optical-transport staging)
    """

    output_stage_dir = resolve_output_stage_directory(config)
    output_stage_dir.mkdir(parents=True, exist_ok=True)
    transport_stage_dir = resolve_transport_photons_stage_directory(config)
    transport_stage_dir.mkdir(parents=True, exist_ok=True)
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
    """Build a macro command block from config state.

    The emitted command order is stable:
    1. optional output commands
    2. geometry commands from `SimConfig.geometry_commands()`
    3. optional `/run/initialize`
    """

    commands: list[str] = []
    if include_output:
        commands.extend(output_commands(config))
    commands.extend(config.geometry_commands())
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
    """Write a macro file from config.

    Parameters
    ----------
    config:
        Source simulation configuration.
    macro_path:
        Destination macro file path. When omitted, defaults to:
        `<effective-root>/<runname?>/macros/<runname or generated_from_config>.mac`
        where effective-root falls back to `data/` if output_path is
        missing/unresolvable.
    include_output:
        Include `/output/*` commands before geometry commands.
    include_run_initialize:
        Append `/run/initialize` at end of emitted block.
    create_output_directories:
        When `True`, create resolved simulation output stage directory before
        writing the macro. This keeps directory creation on the Python side.
    overwrite:
        If `False`, raise `FileExistsError` when destination already exists.
    """

    if macro_path is None:
        path = resolve_default_macro_path(config)
    else:
        path = Path(macro_path)

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

    Parameters
    ----------
    macro_path:
        Existing macro file path.
    commands:
        Expected to be a list of strings.
    key_name:
        Validation label used in error messages.
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


def apply_geometry_to_macro(config: SimConfig, macro_path: str | Path) -> None:
    """Patch geometry commands in an existing macro file in-place.

    Update strategy:
    - Replace existing lines when the command prefix matches one of the
      generated geometry command prefixes.
    - Preserve comments, blank lines, and unrelated macro commands.
    - Insert still-missing geometry commands immediately before
      `/run/initialize` if present, otherwise append them at file end.
    """

    path = Path(macro_path)
    if not path.exists():
        raise FileNotFoundError(f"Macro file not found: {path}")

    lines = path.read_text(encoding="utf-8").splitlines()
    replacements = {cmd.split()[0]: cmd for cmd in config.geometry_commands()}

    replaced: set[str] = set()
    out_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            out_lines.append(line)
            continue

        prefix = stripped.split()[0]
        if prefix in replacements:
            out_lines.append(replacements[prefix])
            replaced.add(prefix)
            continue
        out_lines.append(line)

    missing = [prefix for prefix in replacements if prefix not in replaced]
    if missing:
        insert_idx = next(
            (i for i, line in enumerate(out_lines) if line.strip() == "/run/initialize"),
            len(out_lines),
        )
        out_lines[insert_idx:insert_idx] = [replacements[prefix] for prefix in missing]

    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
