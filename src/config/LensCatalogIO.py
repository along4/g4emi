"""I/O helpers for the lens catalog."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from src.config.LensCatalog import (
        LensCatalogContext,
        LensCatalogEntryDefinition,
        LensCatalogIndex,
        LoadedLens,
    )
    from src.config.utilsConfig import repo_root
except ModuleNotFoundError:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from src.config.LensCatalog import (
        LensCatalogContext,
        LensCatalogEntryDefinition,
        LensCatalogIndex,
        LoadedLens,
    )
    from src.config.utilsConfig import repo_root

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - environment dependent
    yaml = None


DEFAULT_LENS_CATALOG_PATH = repo_root() / "lenses" / "catalog.yaml"
DEFAULT_ZMX_SUBDIR = "zmxFiles"
DEFAULT_SMX_SUBDIR = "smxFiles"


def _require_yaml_dependency() -> Any:
    if yaml is None:
        raise ModuleNotFoundError(
            "PyYAML is required for lens catalog IO. "
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


def load_catalog_context(
    catalog_path: str | Path = DEFAULT_LENS_CATALOG_PATH,
) -> LensCatalogContext:
    """Load lens catalog index and filesystem context."""

    path = Path(catalog_path).resolve()
    parsed = _load_yaml_mapping(path)
    index = LensCatalogIndex.model_validate(parsed)
    return LensCatalogContext(index=index, catalog_path=str(path))


def available_lenses(
    catalog_path: str | Path = DEFAULT_LENS_CATALOG_PATH,
) -> list[str]:
    """Return sorted lens IDs in the catalog."""

    context = load_catalog_context(catalog_path)
    return sorted(context.index.lenses.keys())


def _resolve_asset_path(
    *,
    token: str,
    catalog_dir: Path,
    default_subdir: str,
) -> Path:
    """Resolve one asset token into an absolute path."""

    candidate = Path(token).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()

    # If token already includes a subdirectory, honor it from catalog root.
    if len(candidate.parts) > 1:
        return (catalog_dir / candidate).resolve()

    return (catalog_dir / default_subdir / candidate.name).resolve()


def _entry_definition(context: LensCatalogContext, lens_id: str) -> LensCatalogEntryDefinition:
    entry = context.index.lenses.get(lens_id)
    if entry is None:
        raise KeyError(
            f"Unknown lens ID '{lens_id}'. Available: {sorted(context.index.lenses.keys())}"
        )
    return entry


def load_lens_definition(
    lens_id: str,
    *,
    catalog_path: str | Path = DEFAULT_LENS_CATALOG_PATH,
) -> LensCatalogEntryDefinition:
    """Load one lens definition block from the catalog."""

    context = load_catalog_context(catalog_path)
    return _entry_definition(context, lens_id)


def load_lens(
    lens_id: str | None = None,
    *,
    catalog_path: str | Path = DEFAULT_LENS_CATALOG_PATH,
) -> LoadedLens:
    """Load a resolved lens entry with absolute zmx/smx paths."""

    context = load_catalog_context(catalog_path)
    selected_id = lens_id or context.index.default
    entry = _entry_definition(context, selected_id)
    catalog_dir = Path(context.catalog_path).parent

    zmx_path = _resolve_asset_path(
        token=entry.zmx_file,
        catalog_dir=catalog_dir,
        default_subdir=DEFAULT_ZMX_SUBDIR,
    )
    if not zmx_path.exists():
        raise FileNotFoundError(
            f"Lens catalog entry '{selected_id}' zmx file not found: {zmx_path}"
        )

    if entry.smx_file is not None:
        smx_path = _resolve_asset_path(
            token=entry.smx_file,
            catalog_dir=catalog_dir,
            default_subdir=DEFAULT_SMX_SUBDIR,
        )
        if not smx_path.exists():
            raise FileNotFoundError(
                f"Lens catalog entry '{selected_id}' smx file not found: {smx_path}"
            )
    else:
        inferred_smx = (
            catalog_dir / DEFAULT_SMX_SUBDIR / f"{Path(entry.zmx_file).stem}.smx"
        ).resolve()
        smx_path = inferred_smx if inferred_smx.exists() else None

    return LoadedLens.model_validate(
        {
            "id": selected_id,
            "name": entry.name,
            "description": entry.description,
            "zmxPath": zmx_path,
            "smxPath": smx_path,
        }
    )
