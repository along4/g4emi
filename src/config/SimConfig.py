"""Pydantic simulation configuration for lens-aware g4emi macro geometry."""

from __future__ import annotations

import argparse
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

    Key behavior:
    - Accepts a lens list of size 1 or 2.
    - Loads `.zmx` lens models through `src.optics.LensModels`.
    - Exposes derived geometry (diameter and length) for placement logic.
    """

    model_config = ConfigDict(validate_assignment=True)

    # Lens list that drives optical geometry extraction.
    lenses: list[str] = Field(default_factory=lambda: ["canon50"])

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
    def validate_lens_count(self) -> "SimConfig":
        if not (1 <= len(self.lenses) <= 2):
            raise ValueError("`lenses` must contain 1 or 2 entries.")
        return self

    def lens_models(self) -> list[LensModel]:
        """Load lens models from `self.lenses` references."""

        return load_lens_models(self.lenses)

    def primary_lens(self) -> LensModel:
        """Return the first (object-side) lens model."""

        return self.lens_models()[0]

    def resolved_sensor_diameter_mm(self) -> float:
        """Return sensor diameter in mm.

        Priority:
        1. explicit `sensor_diameter_mm`
        2. primary lens clear diameter
        """

        if self.sensor_diameter_mm is not None:
            return self.sensor_diameter_mm
        return lens_clear_diameter_mm(self.primary_lens())

    def lens_stack_length_total_mm(self) -> float:
        """Return sum of extracted lens stack lengths for all configured lenses."""

        return sum(lens_stack_length_mm(lens) for lens in self.lens_models())

    def lens_geometry_summary(self) -> list[dict[str, Any]]:
        """Return a compact geometry summary for each configured lens."""

        summary: list[dict[str, Any]] = []
        for lens in self.lens_models():
            summary.append(
                {
                    "name": lens.name,
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
        """Return aperture radius in mm, or None to disable aperture command."""

        if not self.use_aperture_mask:
            return None
        if self.aperture_radius_mm is not None:
            return self.aperture_radius_mm
        return 0.5 * self.resolved_sensor_diameter_mm()

    def sensor_center_z_mm(self) -> float:
        """Compute sensor center z-position in mm from back-face standoff."""

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
        """Build Geant4 geometry commands from this configuration."""

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
        """Replace or insert geometry commands in a Geant4 macro file."""

        path = Path(macro_path)
        if not path.exists():
            raise FileNotFoundError(f"Macro file not found: {path}")

        lines = path.read_text(encoding="utf-8").splitlines()
        replacements = {cmd.split()[0]: cmd for cmd in self.geometry_commands()}

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

        missing = [p for p in replacements if p not in replaced]
        if missing:
            insert_idx = next(
                (i for i, line in enumerate(out_lines) if line.strip() == "/run/initialize"),
                len(out_lines),
            )
            out_lines[insert_idx:insert_idx] = [replacements[p] for p in missing]

        path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration and derived lens geometry into a dict."""

        out = self.model_dump(mode="json")
        out["lens_geometry"] = self.lens_geometry_summary()
        out["lens_stack_length_total_mm"] = self.lens_stack_length_total_mm()
        out["resolved_sensor_diameter_mm"] = self.resolved_sensor_diameter_mm()
        return out


def default_single_lens_config() -> SimConfig:
    """Return default single-lens config (Canon EF50mm preset)."""

    return SimConfig(lenses=["canon50"])


def _cli() -> None:
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
