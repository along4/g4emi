"""Lens metadata models and Zemax `.zmx` geometry extraction utilities.

This module centralizes all parsing/inference logic related to optical lens
files so higher-level orchestration code (for example `SimConfig`) can consume
clean, validated geometry values without knowing Zemax text details.

Design goals:
- Keep parsing deterministic and explicit.
- Preserve traceability back to source `.zmx` file path.
- Expose practical geometry values in millimeters:
  - clear aperture diameter
  - approximate lens assembly length
  - image-plane coverage metadata (image-circle and inferred sensor size)

Terminology used here:
- "semi-diameter": radial half-size from optic axis to edge.
- "clear diameter": full diameter, usually 2 * semi-diameter.
- "track length": sum of finite DISZ separations in the sequential prescription.
"""

from __future__ import annotations

import math
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict, Field


# Capture the leading unit token (for example "MM") from `UNIT` line.
_UNIT_RE = re.compile(r"^\s*UNIT\s+([A-Za-z]+)\b")
# Start of each surface block in sequential Zemax files.
_SURF_RE = re.compile(r"^\s*SURF\s+(\d+)\b")
# First numeric value following `DIAM` is the surface aperture value.
_DIAM_RE = re.compile(r"^\s*DIAM\s+([-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?)\b")
# `DISZ` carries spacing to the next surface, may be finite or INFINITY.
_DISZ_RE = re.compile(r"^\s*DISZ\s+(.+?)\s*$")
# Presence of `GLAS` marks a refractive element surface.
_GLAS_RE = re.compile(r"^\s*GLAS\b")


class LensSurface(BaseModel):
    """Compact representation of one parsed Zemax surface.

    Field semantics:
    - `index`: Zemax surface index (`SURF n`).
    - `semi_diameter_mm`: parsed `DIAM` value for this surface.
    - `disz_to_next_mm`: finite distance to next surface (`DISZ`), if present.
    - `has_glass`: true if this surface block contains a `GLAS` entry.
    """

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    semi_diameter_mm: float = 0.0
    disz_to_next_mm: float | None = None
    has_glass: bool = False


class LensModel(BaseModel):
    """Lens metadata and derived geometry extracted from a `.zmx` file.

    This model is immutable (`frozen=True`) so derived geometric values cannot
    drift from the source parse once constructed.

    High-level geometric outputs:
    - `clear_diameter_mm`: largest usable aperture diameter in the prescription.
    - `lens_stack_length_mm`: front-to-back lens-group depth approximation
      bounded by first/last surfaces that reference glass.
    - `image_circle_diameter_mm`: image-plane coverage inferred from last
      surface aperture.
    - `inferred_sensor_width_mm_3x2`/`...height...`: 3:2-format rectangle
      inferred from the image-circle diagonal.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    zmx_path: Path
    surfaces: list[LensSurface]

    max_surface_semidiameter_mm: float = Field(gt=0.0)
    clear_diameter_mm: float = Field(gt=0.0)
    total_track_length_mm: float = Field(ge=0.0)
    lens_stack_length_mm: float = Field(ge=0.0)
    image_surface_index: int = Field(ge=0)
    image_plane_semidiameter_mm: float = Field(ge=0.0)
    image_circle_diameter_mm: float = Field(ge=0.0)
    inferred_sensor_width_mm_3x2: float = Field(ge=0.0)
    inferred_sensor_height_mm_3x2: float = Field(ge=0.0)

    @classmethod
    def from_zmx(
        cls,
        zmx_path: str | Path,
        *,
        name: str | None = None,
        diam_token_is_semidiameter: bool = True,
    ) -> "LensModel":
        """Construct a LensModel by parsing a Zemax `.zmx` file.

        Parsing algorithm summary:
        1. Scan the file line-by-line and build `LensSurface` blocks between
           successive `SURF` markers.
        2. Record first-seen UNIT token and validate that it is `MM`.
        3. Extract relevant per-surface values (`DIAM`, `DISZ`, `GLAS` flag).
        4. Compute aggregate geometric metrics from parsed surfaces.

        Geometry extraction details:
        - `clear_diameter_mm`:
          `max(DIAM)` or `2*max(DIAM)` depending on
          `diam_token_is_semidiameter`.
        - `total_track_length_mm`:
          sum of finite `DISZ` values for surfaces with index > 0; gives a
          whole-prescription axial path length proxy.
        - `lens_stack_length_mm`:
          sum of finite `DISZ` from first to last surface that includes `GLAS`;
          this isolates physical lens-group depth from very long object/image
          distances.
        - `image_plane_semidiameter_mm`:
          aperture value on the last indexed surface (treated as image plane).
        - `image_circle_diameter_mm`:
          full image-circle diameter inferred from image semidiameter.
        - `inferred_sensor_width_mm_3x2` / `inferred_sensor_height_mm_3x2`:
          rectangle inferred from a 3:2 aspect ratio assumption where the
          diagonal equals image-circle diameter.

        Important assumptions/caveats:
        - Sequential `.zmx` style with explicit `SURF`/`DIAM`/`DISZ` tokens.
        - Image-plane interpreted as highest surface index.
        - Inferred sensor size is not guaranteed to match a real sensor unless
          the lens was designed for that exact format.
        """

        path = Path(zmx_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Lens file not found: {path}")

        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()

        # File-level lens unit (expected MM from these datasets).
        unit: str | None = None
        # Ordered list of parsed surface records.
        surfaces: list[LensSurface] = []

        # Mutable parse state for one surface block.
        current_index: int | None = None
        current_diam = 0.0
        current_disz: float | None = None
        current_has_glass = False

        def flush_surface() -> None:
            """Finalize current mutable surface state into `surfaces` list."""

            nonlocal current_index, current_diam, current_disz, current_has_glass
            if current_index is None:
                return
            surfaces.append(
                LensSurface(
                    index=current_index,
                    semi_diameter_mm=current_diam,
                    disz_to_next_mm=current_disz,
                    has_glass=current_has_glass,
                )
            )
            current_index = None
            current_diam = 0.0
            current_disz = None
            current_has_glass = False

        for line in lines:
            # Capture unit once from the first matching UNIT line.
            unit_match = _UNIT_RE.match(line)
            if unit_match and unit is None:
                unit = unit_match.group(1).upper()

            # New SURF begins: commit prior block, then reset state.
            surf_match = _SURF_RE.match(line)
            if surf_match:
                flush_surface()
                current_index = int(surf_match.group(1))
                continue

            # Ignore non-surface lines once not inside a SURF block.
            if current_index is None:
                continue

            # Keep the leading DIAM numeric token as surface semi-diameter.
            diam_match = _DIAM_RE.match(line)
            if diam_match:
                value = float(diam_match.group(1))
                if value > 0.0:
                    current_diam = value
                continue

            # Parse finite DISZ spacing; skip INFINITY sentinel.
            disz_match = _DISZ_RE.match(line)
            if disz_match:
                token = disz_match.group(1).strip().split()[0].upper()
                if token != "INFINITY":
                    current_disz = float(token)
                continue

            # Any GLAS line marks this surface as part of refractive lens stack.
            if _GLAS_RE.match(line):
                current_has_glass = True

        # Commit the final surface block at EOF.
        flush_surface()

        if unit and unit != "MM":
            raise ValueError(
                f"Unsupported lens units '{unit}' in {path}; expected UNIT MM."
            )
        if not surfaces:
            raise ValueError(f"No SURF blocks found in {path}")

        diam_values = [
            s.semi_diameter_mm for s in surfaces if s.semi_diameter_mm > 0.0
        ]
        if not diam_values:
            raise ValueError(f"No positive DIAM values found in {path}")

        max_semidiameter = max(diam_values)
        clear_diameter = (
            2.0 * max_semidiameter if diam_token_is_semidiameter else max_semidiameter
        )

        total_track_length_mm = sum(
            s.disz_to_next_mm
            for s in surfaces
            if s.index > 0 and s.disz_to_next_mm is not None
        )

        # Identify physical lens stack extent using GLAS-tagged surfaces.
        glass_indices = [s.index for s in surfaces if s.has_glass]
        lens_stack_length_mm = 0.0
        if glass_indices:
            first_glass = min(glass_indices)
            last_glass = max(glass_indices)
            lens_stack_length_mm = sum(
                s.disz_to_next_mm
                for s in surfaces
                if s.disz_to_next_mm is not None and first_glass <= s.index <= last_glass
            )

        # Image surface approximated by largest SURF index in sequential model.
        image_surface = max(surfaces, key=lambda s: s.index)
        image_plane_semidiameter_mm = max(0.0, image_surface.semi_diameter_mm)
        image_circle_diameter_mm = (
            2.0 * image_plane_semidiameter_mm
            if diam_token_is_semidiameter
            else image_plane_semidiameter_mm
        )

        # Infer 3:2 sensor dimensions from diagonal=image_circle_diameter_mm.
        # This is inferred convenience metadata, not explicit file truth.
        inferred_sensor_width_mm_3x2 = image_circle_diameter_mm * (3.0 / math.sqrt(13.0))
        inferred_sensor_height_mm_3x2 = image_circle_diameter_mm * (2.0 / math.sqrt(13.0))

        return cls(
            name=name or path.stem,
            zmx_path=path,
            surfaces=surfaces,
            max_surface_semidiameter_mm=max_semidiameter,
            clear_diameter_mm=clear_diameter,
            total_track_length_mm=total_track_length_mm,
            lens_stack_length_mm=lens_stack_length_mm,
            image_surface_index=image_surface.index,
            image_plane_semidiameter_mm=image_plane_semidiameter_mm,
            image_circle_diameter_mm=image_circle_diameter_mm,
            inferred_sensor_width_mm_3x2=inferred_sensor_width_mm_3x2,
            inferred_sensor_height_mm_3x2=inferred_sensor_height_mm_3x2,
        )


def _default_zmx_dir() -> Path:
    """Return default repository location for bundled Zemax files."""

    return Path(__file__).resolve().parent / "zmxFiles"


def resolve_lens_path(lens_ref: str | Path) -> Path:
    """Resolve a lens reference into a concrete `.zmx` file path.

    Resolution order:
    1. Exact user-provided filesystem path.
    2. Known aliases (`canon50`, `nikkor80-200`, etc.).
    3. File under default zmx directory.
    4. File stem under default directory with `.zmx` suffix added.

    Accepted lens_ref forms:
    - absolute or relative path
    - alias token
    - filename or stem for file in `src/optics/zmxFiles`
    """

    if isinstance(lens_ref, Path):
        candidate = lens_ref
    else:
        alias = lens_ref.strip().lower()
        alias_map = {
            "canon50": "CanonEF50mmf1.0L.zmx",
            "canon_ef50": "CanonEF50mmf1.0L.zmx",
            "nikkor80-200": "Nikkor80-200mmf2.8D.zmx",
            "nikkor80_200": "Nikkor80-200mmf2.8D.zmx",
        }
        candidate = Path(alias_map.get(alias, lens_ref))

    # Direct path hit (absolute or cwd-relative).
    if candidate.exists():
        return candidate.resolve()

    zmx_dir = _default_zmx_dir()

    # Try path under default bundled zmx directory.
    in_dir = zmx_dir / candidate
    if in_dir.exists():
        return in_dir.resolve()

    # Try adding .zmx extension under default bundled directory.
    if candidate.suffix.lower() != ".zmx":
        with_ext = zmx_dir / f"{candidate.name}.zmx"
        if with_ext.exists():
            return with_ext.resolve()

    raise FileNotFoundError(f"Unable to resolve lens reference: {lens_ref}")


def load_lens_models(lenses: list[str | Path]) -> list[LensModel]:
    """Load and parse a sequence of lenses from path/alias references.

    The returned list order matches the input order. Caller can treat this as
    optical ordering (for example lens 1 then lens 2 in a stack).
    """

    models: list[LensModel] = []
    for lens_ref in lenses:
        path = resolve_lens_path(lens_ref)
        models.append(LensModel.from_zmx(path))
    return models


def lens_clear_diameter_mm(lens: LensModel) -> float:
    """Return clear aperture diameter (mm) from a parsed lens model."""

    return lens.clear_diameter_mm


def lens_stack_length_mm(lens: LensModel) -> float:
    """Return extracted front-to-back lens stack length (mm)."""

    return lens.lens_stack_length_mm


def lens_image_circle_diameter_mm(lens: LensModel) -> float:
    """Return image-circle diameter (mm) inferred from image-plane DIAM."""

    return lens.image_circle_diameter_mm
