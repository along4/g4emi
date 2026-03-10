"""Pydantic models for scintillator catalog data.

These models define a Python-native representation for reusable scintillator
material definitions and file-backed optical curves.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Base model with strict validation defaults."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
    )


class ScalarWithUnit(StrictModel):
    """Dimensioned scalar used for composition and optical constants."""

    value: float
    unit: str = Field(min_length=1)


class CurveReference(StrictModel):
    """Reference to a curve file with axis unit metadata."""

    path: str = Field(min_length=1)
    x_unit: str = Field(alias="xUnit", min_length=1)
    y_unit: str = Field(alias="yUnit", min_length=1)


class CompositionDefinition(StrictModel):
    """Bulk composition for scintillator material creation."""

    density: ScalarWithUnit
    atoms: dict[str, int] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_atoms(self) -> "CompositionDefinition":
        for symbol, count in self.atoms.items():
            if not symbol.strip():
                raise ValueError("composition.atoms element symbol must be non-empty.")
            if count <= 0:
                raise ValueError(
                    f"composition.atoms['{symbol}'] must be positive, got {count}."
                )
        return self


class OpticalCurvesDefinition(StrictModel):
    """Curve references for required scintillator optical properties."""

    r_index: CurveReference = Field(alias="rIndex")
    abs_length: CurveReference = Field(alias="absLength")
    scint_spectrum: CurveReference = Field(alias="scintSpectrum")


class ScintillationTimeComponentDefinition(StrictModel):
    """Single scintillation decay component for catalog constants."""

    time_constant: ScalarWithUnit = Field(alias="timeConstant")
    yield_fraction: float = Field(alias="yieldFraction", ge=0)


class ScintillationTimeComponentsByExcitationDefinition(StrictModel):
    """Catalog time profiles keyed by excitation/source family."""

    default: list[ScintillationTimeComponentDefinition] | None = None
    neutron: list[ScintillationTimeComponentDefinition] | None = None
    gamma: list[ScintillationTimeComponentDefinition] | None = None

    @staticmethod
    def _validate_profile(
        profile_name: str,
        components: list[ScintillationTimeComponentDefinition],
    ) -> None:
        if len(components) != 3:
            raise ValueError(
                f"`optical.constants.timeComponents.{profile_name}` must define exactly 3 components."
            )
        total = sum(component.yield_fraction for component in components)
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1.0e-9):
            raise ValueError(
                "`optical.constants.timeComponents."
                f"{profile_name}` yield fractions must sum to ~1.0."
            )
        active_component_count = sum(
            1
            for component in components
            if component.yield_fraction > 0.0 and component.time_constant.value > 0.0
        )
        if active_component_count == 0:
            raise ValueError(
                "`optical.constants.timeComponents."
                f"{profile_name}` must define at least one active component "
                "(`yieldFraction > 0` and `timeConstant > 0`)."
            )

    @model_validator(mode="after")
    def validate_profiles(
        self,
    ) -> "ScintillationTimeComponentsByExcitationDefinition":
        """Require at least one profile and validate each profile independently."""

        present = False
        for profile_name in ("default", "neutron", "gamma"):
            components = getattr(self, profile_name)
            if components is None:
                continue
            present = True
            self._validate_profile(profile_name, components)
        if not present:
            raise ValueError(
                "`optical.constants.timeComponents` must include at least one "
                "profile: `default`, `neutron`, or `gamma`."
            )
        return self


class OpticalConstantsDefinition(StrictModel):
    """Energy-independent optical constants."""

    scint_yield: ScalarWithUnit = Field(alias="scintYield")
    resolution_scale: float = Field(alias="resolutionScale", gt=0)
    time_components: ScintillationTimeComponentsByExcitationDefinition = Field(
        alias="timeComponents"
    )


class OpticalDefinition(StrictModel):
    """Full optical block for a scintillator entry."""

    curves: OpticalCurvesDefinition
    constants: OpticalConstantsDefinition


class ScintillatorMaterialDefinition(StrictModel):
    """Single catalog material entry stored in `materials/*.yaml`."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    composition: CompositionDefinition
    optical: OpticalDefinition


class ScintillatorCatalogIndex(StrictModel):
    """Catalog index file model (`catalog.yaml`)."""

    version: int = Field(ge=1)
    default: str = Field(min_length=1)
    materials: dict[str, str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_default_key(self) -> "ScintillatorCatalogIndex":
        if self.default not in self.materials:
            raise ValueError(
                f"catalog default '{self.default}' not found in materials mapping."
            )
        return self


class CurveData(StrictModel):
    """Resolved curve data loaded from CSV/text files."""

    x_unit: str = Field(alias="xUnit", min_length=1)
    y_unit: str = Field(alias="yUnit", min_length=1)
    energy: list[float] = Field(min_length=1)
    value: list[float] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_curve_lengths(self) -> "CurveData":
        if len(self.energy) != len(self.value):
            raise ValueError("curve energy/value lengths must match.")
        previous = None
        for current in self.energy:
            if previous is not None and current <= previous:
                raise ValueError("curve energy values must be strictly increasing.")
            previous = current
        return self


class LoadedScintillator(StrictModel):
    """Resolved scintillator definition with loaded curve payloads."""

    material: ScintillatorMaterialDefinition
    r_index: CurveData = Field(alias="rIndex")
    abs_length: CurveData = Field(alias="absLength")
    scint_spectrum: CurveData = Field(alias="scintSpectrum")

    @model_validator(mode="after")
    def validate_shared_energy_grid(self) -> "LoadedScintillator":
        reference = self.r_index.energy
        if self.abs_length.energy != reference:
            raise ValueError("absLength energy grid must match rIndex energy grid.")
        if self.scint_spectrum.energy != reference:
            raise ValueError("scintSpectrum energy grid must match rIndex energy grid.")
        return self


@dataclass(frozen=True)
class CatalogContext:
    """Loaded catalog index and filesystem context."""

    index: ScintillatorCatalogIndex
    catalog_path: str
