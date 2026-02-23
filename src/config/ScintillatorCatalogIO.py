"""I/O helpers for the scintillator catalog."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

try:
    from src.config.ScintillatorCatalog import (
        CatalogContext,
        CurveData,
        ScintillatorCatalogIndex,
        ScintillatorMaterialDefinition,
        LoadedScintillator,
    )
    from src.config.utilsConfig import repo_root
except ModuleNotFoundError:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from src.config.ScintillatorCatalog import (
        CatalogContext,
        CurveData,
        ScintillatorCatalogIndex,
        ScintillatorMaterialDefinition,
        LoadedScintillator,
    )
    from src.config.utilsConfig import repo_root

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - environment dependent
    yaml = None


DEFAULT_SCINTILLATOR_CATALOG_PATH = (
    repo_root() / "scintillators" / "catalog.yaml"
)


def _require_yaml_dependency() -> Any:
    if yaml is None:
        raise ModuleNotFoundError(
            "PyYAML is required for scintillator catalog IO. "
            "Install it in your environment (for example: pixi add pyyaml)."
        )
    return yaml


def _load_yaml_mapping(yaml_path: str | Path) -> dict[str, Any]:
    module_yaml = _require_yaml_dependency()
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {path}")

    parsed = module_yaml.safe_load(path.read_text(encoding="utf-8"))
    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        raise ValueError(f"YAML at {path} must be a mapping/object.")
    return parsed


def _split_curve_line(line: str) -> list[str]:
    """Split one curve row into tokens (supports comma or whitespace)."""

    if "," in line:
        return [token.strip() for token in line.split(",")]
    return [token.strip() for token in line.split()]


def _load_curve(path: Path, *, x_unit: str, y_unit: str) -> CurveData:
    if not path.exists():
        raise FileNotFoundError(f"Curve file not found: {path}")

    energy: list[float] = []
    value: list[float] = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        tokens = _split_curve_line(line)
        if len(tokens) < 2:
            raise ValueError(
                f"Curve row must have two columns '<energy> <value>', got: {line!r}"
            )

        # Skip a header row like "energy_eV,value".
        if not energy and re.search(r"[A-Za-z_]", tokens[0]):
            continue

        try:
            e = float(tokens[0])
            v = float(tokens[1])
        except ValueError as exc:
            raise ValueError(f"Curve row has non-numeric data: {line!r}") from exc

        energy.append(e)
        value.append(v)

    return CurveData.model_validate(
        {
            "xUnit": x_unit,
            "yUnit": y_unit,
            "energy": energy,
            "value": value,
        }
    )


def load_catalog_context(
    catalog_path: str | Path = DEFAULT_SCINTILLATOR_CATALOG_PATH,
) -> CatalogContext:
    """Load catalog index and filesystem context."""

    path = Path(catalog_path).resolve()
    parsed = _load_yaml_mapping(path)
    index = ScintillatorCatalogIndex.model_validate(parsed)
    return CatalogContext(index=index, catalog_path=str(path))


def available_scintillators(
    catalog_path: str | Path = DEFAULT_SCINTILLATOR_CATALOG_PATH,
) -> list[str]:
    """Return sorted material IDs in the catalog."""

    context = load_catalog_context(catalog_path)
    return sorted(context.index.materials.keys())


def _resolve_material_path(context: CatalogContext, material_id: str) -> Path:
    catalog_file = Path(context.catalog_path)
    rel = context.index.materials.get(material_id)
    if rel is None:
        raise KeyError(
            f"Unknown scintillator ID '{material_id}'. "
            f"Available: {sorted(context.index.materials.keys())}"
        )
    return (catalog_file.parent / rel).resolve()


def load_scintillator_definition(
    material_id: str,
    *,
    catalog_path: str | Path = DEFAULT_SCINTILLATOR_CATALOG_PATH,
) -> ScintillatorMaterialDefinition:
    """Load a single `materials/*.yaml` definition from the catalog index."""

    context = load_catalog_context(catalog_path)
    material_path = _resolve_material_path(context, material_id)
    parsed = _load_yaml_mapping(material_path)
    material = ScintillatorMaterialDefinition.model_validate(parsed)
    if material.id != material_id:
        raise ValueError(
            f"Material file id mismatch: expected '{material_id}', got '{material.id}'."
        )
    return material


def load_scintillator(
    material_id: str | None = None,
    *,
    catalog_path: str | Path = DEFAULT_SCINTILLATOR_CATALOG_PATH,
) -> LoadedScintillator:
    """Load a resolved scintillator entry with curve payloads.

    When `material_id` is omitted, the catalog default is used.
    """

    context = load_catalog_context(catalog_path)
    selected_id = material_id or context.index.default

    material_path = _resolve_material_path(context, selected_id)
    material = ScintillatorMaterialDefinition.model_validate(_load_yaml_mapping(material_path))

    if material.id != selected_id:
        raise ValueError(
            f"Material file id mismatch: expected '{selected_id}', got '{material.id}'."
        )

    catalog_dir = Path(context.catalog_path).parent
    curves = material.optical.curves
    r_index = _load_curve(
        (catalog_dir / curves.r_index.path).resolve(),
        x_unit=curves.r_index.x_unit,
        y_unit=curves.r_index.y_unit,
    )
    abs_length = _load_curve(
        (catalog_dir / curves.abs_length.path).resolve(),
        x_unit=curves.abs_length.x_unit,
        y_unit=curves.abs_length.y_unit,
    )
    scint_spectrum = _load_curve(
        (catalog_dir / curves.scint_spectrum.path).resolve(),
        x_unit=curves.scint_spectrum.x_unit,
        y_unit=curves.scint_spectrum.y_unit,
    )

    return LoadedScintillator.model_validate(
        {
            "material": material.model_dump(mode="python"),
            "rIndex": r_index.model_dump(mode="python", by_alias=True),
            "absLength": abs_length.model_dump(mode="python", by_alias=True),
            "scintSpectrum": scint_spectrum.model_dump(mode="python", by_alias=True),
        }
    )
