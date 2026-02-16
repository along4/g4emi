"""Pydantic simulation configuration for lens-aware g4emi geometry macros.

This module binds together three concerns:
1. User-facing simulation geometry parameters (scintillator/sensor).
2. Lens-driven geometry extraction from `.zmx` models.
3. Deterministic macro-file rewriting for Geant4 command inputs.

The intent is to keep geometry choices declarative and reproducible:
- A lens list (1-2 lenses) is the optical input.
- Derived lens quantities (diameter/length/image-circle) come from `LensModels`.
- Geant4 macro commands are generated from one validated config object.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

try:
    from src.optics.LensModels import (
        LensModel,
        lens_clear_diameter_mm,
        lens_image_circle_diameter_mm,
        lens_stack_length_mm,
        load_lens_models,
    )
except ModuleNotFoundError:
    # Support direct script execution: `python src/config/SimConfig.py`.
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from src.optics.LensModels import (
        LensModel,
        lens_clear_diameter_mm,
        lens_image_circle_diameter_mm,
        lens_stack_length_mm,
        load_lens_models,
    )


class SimConfig(BaseModel):
    """High-level geometry + lens-stack configuration for g4emi.

    Core behavior:
    - Accepts one or two lenses through `lenses`.
    - Resolves and loads corresponding `.zmx` models via `LensModels`.
    - Exposes derived lens geometry used for simulation setup:
      clear diameter, lens length, image-circle metadata.
    - Produces Geant4 macro commands for scintillator/sensor configuration.

    Modeling convention:
    - `lenses[0]` is treated as the primary/object-side lens for defaults.
    - Sensor diameter defaults to primary lens clear diameter unless overridden.
    - Sensor Z placement is computed from requested back-face standoff.
    """

    model_config = ConfigDict(validate_assignment=True)

    # Lens list that drives optical geometry extraction.
    lenses: list[str] = Field(default_factory=lambda: ["canon50"])
    # Lens orientation flag(s): False means nominal orientation, True means reversed.
    # Accepts either:
    # - one bool applied to all configured lenses, or
    # - one bool per lens, e.g. [True, False] for a two-lens stack.
    reversed: bool | list[bool] = False

    # Scintillator geometry.
    scint_material: str = "EJ200"
    scint_x_cm: float = Field(default=10.0, gt=0.0)
    scint_y_cm: float = Field(default=10.0, gt=0.0)
    scint_z_cm: float = Field(default=2.0, gt=0.0)
    scint_pos_x_cm: float = 0.0
    scint_pos_y_cm: float = 0.0
    scint_pos_z_cm: float = 0.0

    # Sensor geometry + placement.
    sensor_thickness_mm: float = Field(default=0.1, gt=0.0)
    sensor_pos_x_cm: float = 0.0
    sensor_pos_y_cm: float = 0.0
    scint_back_to_sensor_mm: float = Field(default=200.0, gt=0.0)
    sensor_diameter_mm: float | None = Field(default=None, gt=0.0)

    # Optional aperture linked to sensor diameter by default.
    use_aperture_mask: bool = True
    aperture_radius_mm: float | None = Field(default=None, gt=0.0)

    # Output metadata.
    output_format: str = "hdf5"
    output_filename: str = "data/photon_sensor_hits"
    output_runname: str = "microscope"

    @model_validator(mode="after")
    def validate_config(self) -> "SimConfig":
        """Run full model validation after creation and assignment.

        This validator is intentionally holistic:
        - structural checks: lens/reversed cardinality
        - geometric checks: sensor diameter, aperture feasibility, placement

        Because `validate_assignment=True`, these checks also run after field
        updates, not only at construction time.
        """

        # Current optical pipeline supports either a single lens or a two-lens
        # macro stack, so enforce that cardinality centrally.
        if not (1 <= len(self.lenses) <= 2):
            raise ValueError("`lenses` must contain 1 or 2 entries.")

        # Per-lens orientation list must align one-to-one with configured lenses.
        if isinstance(self.reversed, list) and len(self.reversed) != len(self.lenses):
            raise ValueError(
                "When `reversed` is a list, it must have the same length as `lenses`."
            )

        self._validate_geometry_invariants()
        return self

    def _scint_back_face_z_mm(self) -> float:
        """Return scintillator +Z face position in mm."""

        return (self.scint_pos_z_cm * 10.0) + (0.5 * self.scint_z_cm * 10.0)

    def _validate_geometry_invariants(self) -> None:
        """Validate geometry relationships that span multiple fields.

        Invariants enforced:
        - Resolved sensor diameter must be strictly positive.
        - Optional aperture radius must fit inside scintillator half-diagonal.
        - Sensor center Z must lie beyond scintillator back face.
        """

        # Resolve effective sensor diameter first, since several downstream
        # constraints depend on it (including default aperture sizing).
        sensor_diameter_mm = self.resolved_sensor_diameter_mm()
        if sensor_diameter_mm <= 0.0:
            raise ValueError(
                f"Resolved sensor diameter must be > 0 mm (got {sensor_diameter_mm})."
            )

        aperture_radius_mm = self.resolved_aperture_radius_mm()
        if aperture_radius_mm is not None:
            scint_half_diag_mm = 0.5 * math.hypot(
                self.scint_x_cm * 10.0, self.scint_y_cm * 10.0
            )
            if aperture_radius_mm > scint_half_diag_mm:
                raise ValueError(
                    "Aperture radius exceeds scintillator half-diagonal: "
                    f"{aperture_radius_mm:.3f} mm > {scint_half_diag_mm:.3f} mm."
                )

        sensor_center_z_mm = self.sensor_center_z_mm()
        scint_back_face_z_mm = self._scint_back_face_z_mm()
        if sensor_center_z_mm <= scint_back_face_z_mm:
            raise ValueError(
                "Sensor center must be beyond scintillator back face: "
                f"{sensor_center_z_mm:.3f} mm <= {scint_back_face_z_mm:.3f} mm."
            )

    def validate_geometry(self) -> "SimConfig":
        """Explicit geometry re-validation helper.

        Useful when callers want an intentional validation checkpoint in scripts.
        Returns `self` to allow chaining.
        """

        self._validate_geometry_invariants()
        return self

    def validated_copy_with_updates(self, **updates: Any) -> "SimConfig":
        """Return a fully validated copy with atomic updates applied.

        This avoids transient invalid states during multi-field edits
        (for example updating `lenses` and `reversed` together).
        """

        # Apply updates against a full snapshot and re-validate once, avoiding
        # transient assignment failures from intermediate invalid states.
        payload = self.model_dump(mode="python")
        payload.update(updates)
        return SimConfig.model_validate(payload)

    def with_geometry_updates(self, **updates: Any) -> "SimConfig":
        """Return a new config with geometry updates atomically validated.

        This is a geometry-oriented alias around `validated_copy_with_updates`
        intended for simulation scripts that frequently tune multiple fields
        together (for example scintillator size + sensor standoff).
        """

        return self.validated_copy_with_updates(**updates)

    def lens_reversed_flags(self) -> list[bool]:
        """Return one orientation flag per configured lens.

        Normalization behavior:
        - scalar bool -> duplicated across all lenses
        - list[bool]  -> returned as-is (validated to same lens count)
        """

        if isinstance(self.reversed, bool):
            return [self.reversed] * len(self.lenses)
        return self.reversed

    def lens_models(self) -> list[LensModel]:
        """Load `LensModel` objects from current lens references.

        Each call re-resolves and re-parses from source files to keep behavior
        stateless and fully dependent on current config values.
        """

        return load_lens_models(self.lenses)

    def primary_lens(self) -> LensModel:
        """Return primary lens model (`lenses[0]`).

        This method exists to make the default-diameter assumption explicit.
        """

        return self.lens_models()[0]

    def resolved_sensor_diameter_mm(self) -> float:
        """Return sensor diameter in mm.

        Priority:
        1. explicit `sensor_diameter_mm`
        2. primary lens clear diameter

        Why this default:
        - In single-lens workflows, sensor capture area typically tracks lens
          clear aperture/image coverage constraints.
        - For two-lens workflows, users can override with `sensor_diameter_mm`
          if they prefer a different sizing policy.
        """

        if self.sensor_diameter_mm is not None:
            return self.sensor_diameter_mm
        return lens_clear_diameter_mm(self.primary_lens())

    def lens_stack_length_total_mm(self) -> float:
        """Return total lens-stack depth (mm) across configured lenses.

        This simply sums per-lens extracted `lens_stack_length_mm` and does not
        include adapters/air gaps between separate lens bodies.
        """

        return sum(lens_stack_length_mm(lens) for lens in self.lens_models())

    def lens_geometry_summary(self) -> list[dict[str, Any]]:
        """Return lens geometry summary records for reporting/serialization.

        Included per lens:
        - clear aperture diameter
        - extracted lens stack length
        - total track length
        - image-plane aperture and inferred image circle
        - inferred 3:2 sensor width/height from image-circle diagonal
        """

        summary: list[dict[str, Any]] = []
        for lens, is_reversed in zip(
            self.lens_models(), self.lens_reversed_flags(), strict=True
        ):
            summary.append(
                {
                    "name": lens.name,
                    "reversed": is_reversed,
                    "zmx_path": str(lens.zmx_path),
                    "clear_diameter_mm": lens_clear_diameter_mm(lens),
                    "lens_stack_length_mm": lens_stack_length_mm(lens),
                    "total_track_length_mm": lens.total_track_length_mm,
                    "image_surface_index": lens.image_surface_index,
                    "image_plane_semidiameter_mm": lens.image_plane_semidiameter_mm,
                    "image_circle_diameter_mm": lens_image_circle_diameter_mm(lens),
                    "inferred_sensor_width_mm_3x2": lens.inferred_sensor_width_mm_3x2,
                    "inferred_sensor_height_mm_3x2": lens.inferred_sensor_height_mm_3x2,
                }
            )
        return summary

    def resolved_aperture_radius_mm(self) -> float | None:
        """Return aperture radius in mm for scintillator-face circular mask.

        Behavior:
        - Returns `None` when aperture masking is disabled.
        - Uses explicit `aperture_radius_mm` when provided.
        - Otherwise derives radius as half of resolved sensor diameter.
        """

        if not self.use_aperture_mask:
            return None
        if self.aperture_radius_mm is not None:
            return self.aperture_radius_mm
        return 0.5 * self.resolved_sensor_diameter_mm()

    def sensor_center_z_mm(self) -> float:
        """Compute sensor center z-position (mm) from configured standoff.

        Definitions:
        - Scintillator back face z:
          `scint_pos_z + scint_z/2`
        - Sensor front face z:
          `scintillator_back_face_z + scint_back_to_sensor_mm`
        - Sensor center z:
          `sensor_front_face_z + sensor_thickness/2`
        """

        scint_center_z_mm = self.scint_pos_z_cm * 10.0
        scint_half_thickness_mm = 0.5 * self.scint_z_cm * 10.0
        sensor_half_thickness_mm = 0.5 * self.sensor_thickness_mm
        return (
            scint_center_z_mm
            + scint_half_thickness_mm
            + self.scint_back_to_sensor_mm
            + sensor_half_thickness_mm
        )

    def geometry_commands(self) -> list[str]:
        """Build Geant4 geometry commands from this configuration.

        Output order is stable and groups commands by subsystem:
        1. scintillator material and dimensions
        2. optional aperture command
        3. sensor dimensions and placement
        """

        sensor_diameter_mm = self.resolved_sensor_diameter_mm()
        aperture_radius_mm = self.resolved_aperture_radius_mm()

        commands = [
            f"/scintillator/geom/material {self.scint_material}",
            f"/scintillator/geom/scintX {self.scint_x_cm:g} cm",
            f"/scintillator/geom/scintY {self.scint_y_cm:g} cm",
            f"/scintillator/geom/scintZ {self.scint_z_cm:g} cm",
            f"/scintillator/geom/posX {self.scint_pos_x_cm:g} cm",
            f"/scintillator/geom/posY {self.scint_pos_y_cm:g} cm",
            f"/scintillator/geom/posZ {self.scint_pos_z_cm:g} cm",
        ]
        if aperture_radius_mm is not None:
            commands.append(
                f"/scintillator/geom/apertureRadius {aperture_radius_mm:.3f} mm"
            )

        commands.extend(
            [
                f"/sensor/geom/sensorX {sensor_diameter_mm:.3f} mm",
                f"/sensor/geom/sensorY {sensor_diameter_mm:.3f} mm",
                f"/sensor/geom/sensorThickness {self.sensor_thickness_mm:g} mm",
                f"/sensor/geom/posX {self.sensor_pos_x_cm:g} cm",
                f"/sensor/geom/posY {self.sensor_pos_y_cm:g} cm",
                f"/sensor/geom/posZ {self.sensor_center_z_mm():.3f} mm",
            ]
        )
        return commands

    def apply_geometry_to_macro(self, macro_path: str | Path) -> None:
        """Apply generated geometry commands to an existing macro in-place.

        Update strategy:
        - Replace any existing lines with matching command prefixes.
        - Preserve comments/blank lines and unrelated commands.
        - Insert still-missing geometry commands immediately before
          `/run/initialize` (or append to end if not present).
        """

        path = Path(macro_path)
        if not path.exists():
            raise FileNotFoundError(f"Macro file not found: {path}")

        lines = path.read_text(encoding="utf-8").splitlines()
        replacements = {cmd.split()[0]: cmd for cmd in self.geometry_commands()}

        replaced: set[str] = set()
        out_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            # Preserve comments/whitespace verbatim for readability.
            if not stripped or stripped.startswith("#"):
                out_lines.append(line)
                continue

            prefix = stripped.split()[0]
            # Replace only known geometry command prefixes.
            if prefix in replacements:
                out_lines.append(replacements[prefix])
                replaced.add(prefix)
                continue
            out_lines.append(line)

        # Inject any missing geometry commands at canonical insertion point.
        missing = [p for p in replacements if p not in replaced]
        if missing:
            insert_idx = next(
                (i for i, line in enumerate(out_lines) if line.strip() == "/run/initialize"),
                len(out_lines),
            )
            out_lines[insert_idx:insert_idx] = [replacements[p] for p in missing]

        path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        """Serialize config plus derived lens geometry into a plain dict.

        Returned payload includes:
        - direct model fields (`model_dump`)
        - derived lens summary list
        - total lens-stack length
        - resolved sensor diameter
        """

        out = self.model_dump(mode="json")
        out["lens_geometry"] = self.lens_geometry_summary()
        out["lens_reversed_flags"] = self.lens_reversed_flags()
        out["lens_stack_length_total_mm"] = self.lens_stack_length_total_mm()
        out["resolved_sensor_diameter_mm"] = self.resolved_sensor_diameter_mm()
        return out


def default_single_lens_config() -> SimConfig:
    """Return default single-lens config (`canon50`)."""

    return SimConfig(lenses=["canon50"])


def _cli() -> None:
    """Command-line entry point for quick inspection and macro patching.

    Typical usage:
    - Inspect lens-derived geometry:
      `python src/config/SimConfig.py --lens canon50`
    - Inspect two-lens geometry:
      `python src/config/SimConfig.py --lens canon50 --lens nikkor80-200`
    - Patch macros in place:
      `python src/config/SimConfig.py --macro sim/macros/microscope_run.mac`
    """

    parser = argparse.ArgumentParser(description="Apply SimConfig geometry to macros.")
    parser.add_argument(
        "--lens",
        action="append",
        default=None,
        help="Lens reference (alias/path). Repeat to configure 1-2 lenses.",
    )
    parser.add_argument(
        "--macro",
        action="append",
        default=[],
        help="Macro file to patch in place (repeat to patch multiple macros).",
    )
    args = parser.parse_args()

    cfg = SimConfig(lenses=args.lens or ["canon50"])

    if not args.macro:
        print("Configured lenses:")
        for entry in cfg.lens_geometry_summary():
            print(
                f"  - {entry['name']}: "
                f"reversed={entry['reversed']}, "
                f"diameter={entry['clear_diameter_mm']:.3f} mm, "
                f"length={entry['lens_stack_length_mm']:.3f} mm, "
                f"image_circle={entry['image_circle_diameter_mm']:.3f} mm"
            )
        print(
            "Total configured lens stack length (mm):",
            f"{cfg.lens_stack_length_total_mm():.3f}",
        )
        print("Resolved sensor diameter (mm):", f"{cfg.resolved_sensor_diameter_mm():.3f}")
        print("Resolved sensor center Z (mm):", f"{cfg.sensor_center_z_mm():.3f}")
        print("Geometry commands:")
        for cmd in cfg.geometry_commands():
            print(cmd)
        return

    for macro in args.macro:
        cfg.apply_geometry_to_macro(macro)
        print(f"Updated macro: {macro}")


if __name__ == "__main__":
    _cli()
