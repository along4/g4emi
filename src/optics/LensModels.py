"""Pydantic lens models and `.zmx` geometry extraction helpers."""

from __future__ import annotations

import math
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict, Field


_UNIT_RE = re.compile(r"^\s*UNIT\s+([A-Za-z]+)\b")
_SURF_RE = re.compile(r"^\s*SURF\s+(\d+)\b")
_DIAM_RE = re.compile(r"^\s*DIAM\s+([-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?)\b")
_DISZ_RE = re.compile(r"^\s*DISZ\s+(.+?)\s*$")
_GLAS_RE = re.compile(r"^\s*GLAS\b")


class LensSurface(BaseModel):
    """Parsed subset of a Zemax surface block."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    semi_diameter_mm: float = 0.0
    disz_to_next_mm: float | None = None
    has_glass: bool = False


class LensModel(BaseModel):
    """Lens metadata and extracted geometry from a `.zmx` file."""

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

        Geometry extraction:
        - `clear_diameter_mm`: max DIAM (or 2x max DIAM if DIAM is semi-diameter).
        - `total_track_length_mm`: sum of finite DISZ values across all non-object surfaces.
        - `lens_stack_length_mm`: sum of finite DISZ from first to last surface containing GLAS.
          This approximates front-to-back lens assembly length (excluding long image-space distance).
        - `image_plane_semidiameter_mm`: DIAM from the last surface (image surface).
        - `image_circle_diameter_mm`: image-plane diameter inferred from the image semidiameter.
        - `inferred_sensor_width_mm_3x2` / `inferred_sensor_height_mm_3x2`:
          sensor size inferred from image-circle diagonal assuming a 3:2 frame.
        """

        path = Path(zmx_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Lens file not found: {path}")

        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()

        unit: str | None = None
        surfaces: list[LensSurface] = []

        current_index: int | None = None
        current_diam = 0.0
        current_disz: float | None = None
        current_has_glass = False

        def flush_surface() -> None:
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
            unit_match = _UNIT_RE.match(line)
            if unit_match and unit is None:
                unit = unit_match.group(1).upper()

            surf_match = _SURF_RE.match(line)
            if surf_match:
                flush_surface()
                current_index = int(surf_match.group(1))
                continue

            if current_index is None:
                continue

            diam_match = _DIAM_RE.match(line)
            if diam_match:
                value = float(diam_match.group(1))
                if value > 0.0:
                    current_diam = value
                continue

            disz_match = _DISZ_RE.match(line)
            if disz_match:
                token = disz_match.group(1).strip().split()[0].upper()
                if token != "INFINITY":
                    current_disz = float(token)
                continue

            if _GLAS_RE.match(line):
                current_has_glass = True

        flush_surface()

        if unit and unit != "MM":
            raise ValueError(
                f"Unsupported lens units '{unit}' in {path}; expected UNIT MM."
            )
        if not surfaces:
            raise ValueError(f"No SURF blocks found in {path}")

        diam_values = [s.semi_diameter_mm for s in surfaces if s.semi_diameter_mm > 0.0]
        if not diam_values:
            raise ValueError(f"No positive DIAM values found in {path}")

        max_semidiameter = max(diam_values)
        clear_diameter = (
            2.0 * max_semidiameter if diam_token_is_semidiameter else max_semidiameter
        )

        total_track_length_mm = sum(
            s.disz_to_next_mm for s in surfaces if s.index > 0 and s.disz_to_next_mm is not None
        )

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

        image_surface = max(surfaces, key=lambda s: s.index)
        image_plane_semidiameter_mm = max(0.0, image_surface.semi_diameter_mm)
        image_circle_diameter_mm = (
            2.0 * image_plane_semidiameter_mm
            if diam_token_is_semidiameter
            else image_plane_semidiameter_mm
        )

        # Infer 3:2 sensor dimensions from diagonal = image circle diameter.
        # This is an inference, not an explicit sensor specification in .zmx.
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
    return Path(__file__).resolve().parent / "zmxFiles"


def resolve_lens_path(lens_ref: str | Path) -> Path:
    """Resolve a lens reference into a concrete `.zmx` file path.

    Accepted forms:
    - absolute or relative filesystem path
    - short aliases: `canon50`, `nikkor80-200`
    - file stem or filename under `src/optics/zmxFiles`
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

    # Direct path hit.
    if candidate.exists():
        return candidate.resolve()

    zmx_dir = _default_zmx_dir()

    # Try path under default zmx directory.
    in_dir = zmx_dir / candidate
    if in_dir.exists():
        return in_dir.resolve()

    # Try adding extension under default zmx directory.
    if candidate.suffix.lower() != ".zmx":
        with_ext = zmx_dir / f"{candidate.name}.zmx"
        if with_ext.exists():
            return with_ext.resolve()

    raise FileNotFoundError(f"Unable to resolve lens reference: {lens_ref}")


def load_lens_models(lenses: list[str | Path]) -> list[LensModel]:
    """Load one or more lens models from references."""

    models: list[LensModel] = []
    for lens_ref in lenses:
        path = resolve_lens_path(lens_ref)
        models.append(LensModel.from_zmx(path))
    return models


def lens_clear_diameter_mm(lens: LensModel) -> float:
    """Return clear diameter (mm) from a LensModel."""

    return lens.clear_diameter_mm


def lens_stack_length_mm(lens: LensModel) -> float:
    """Return extracted lens assembly length (mm) from a LensModel."""

    return lens.lens_stack_length_mm


def lens_image_circle_diameter_mm(lens: LensModel) -> float:
    """Return inferred image-circle diameter (mm) from the image surface."""

    return lens.image_circle_diameter_mm
