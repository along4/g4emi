"""Hierarchical Pydantic models for GEANT4 simulation configuration.

This module defines the authoritative schema for YAML-driven simulation
configuration in Python. The model hierarchy mirrors the user-facing YAML
layout, while Python attribute names stay consistent and type-safe.

Design principles:
- Keep model responsibilities narrow: validation + structure.
- Keep YAML aliases close to their fields to reduce mapping ambiguity.
- Enforce strict input by default so typos surface immediately.
"""

from __future__ import annotations

from datetime import date as DateType
from datetime import datetime
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    """Base model with strict validation defaults.

    Shared behavior for every config block:
    - unknown keys are rejected (`extra="forbid"`)
    - either field-name or alias input is accepted (`populate_by_name=True`)
    - assignment after construction is revalidated (`validate_assignment=True`)
    """

    # Centralized model policy keeps every nested block consistent.
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
    )


class Vec3Mm(StrictModel):
    """Generic 3D coordinate vector in millimeters.

    Used for positions where negative values may be valid.
    """

    x_mm: float
    y_mm: float
    z_mm: float


class Size3Mm(StrictModel):
    """3D size/extent vector in millimeters.

    Unlike :class:`Vec3Mm`, every component must be strictly positive.
    """

    x_mm: float = Field(gt=0)
    y_mm: float = Field(gt=0)
    z_mm: float = Field(gt=0)


class ScintillatorProperties(StrictModel):
    """Optical material table for scintillator definition.

    Fields map directly to common GEANT4 material-property table concepts:
    - `photonEnergy` and `rIndex` are paired lookup arrays
    - `nKEntries` declares the expected table length
    - `timeConstant` describes scintillation decay timing
    """

    name: str
    photon_energy: list[float] = Field(alias="photonEnergy", min_length=1)
    r_index: list[float] = Field(alias="rIndex", min_length=1)
    n_k_entries: int = Field(alias="nKEntries", gt=0)
    time_constant: float = Field(alias="timeConstant", gt=0)

    @model_validator(mode="after")
    def validate_table_lengths(self) -> "ScintillatorProperties":
        """Require optical-table cardinality consistency.

        This check ensures both lookup arrays match the declared `nKEntries`
        value so later table construction cannot silently misalign.
        """

        if len(self.photon_energy) != self.n_k_entries:
            raise ValueError("`photonEnergy` length must match `nKEntries`.")
        if len(self.r_index) != self.n_k_entries:
            raise ValueError("`rIndex` length must match `nKEntries`.")
        return self


class ScintillatorConfig(StrictModel):
    """Scintillator geometry + material properties block."""

    position_mm: Vec3Mm
    dimension_mm: Size3Mm
    properties: ScintillatorProperties


class Vec3(StrictModel):
    """Unitless 3D vector used by GPS angular command blocks."""

    x: float
    y: float
    z: float


class GpsPositionConfig(StrictModel):
    """GPS position distribution configuration."""

    type: str = Field(default="Plane", min_length=1)
    shape: str = Field(default="Circle", min_length=1)
    center_mm: Vec3Mm = Field(alias="centerMm")
    radius_mm: float = Field(alias="radiusMm", gt=0)


class GpsAngularConfig(StrictModel):
    """GPS angular distribution configuration."""

    type: str = Field(default="beam2d", min_length=1)
    rot1: Vec3 = Field(default_factory=lambda: Vec3(x=1.0, y=0.0, z=0.0))
    rot2: Vec3 = Field(default_factory=lambda: Vec3(x=0.0, y=1.0, z=0.0))
    direction: Vec3 = Field(default_factory=lambda: Vec3(x=0.0, y=0.0, z=1.0))


class GpsEnergyConfig(StrictModel):
    """GPS energy distribution configuration."""

    type: str = Field(default="Mono", min_length=1)
    mono_mev: float | None = Field(default=None, alias="monoMeV", gt=0)

    @model_validator(mode="after")
    def validate_energy_payload(self) -> "GpsEnergyConfig":
        """Require mono energy value when GPS type is Mono."""

        if self.type.strip().lower() == "mono" and self.mono_mev is None:
            raise ValueError("`source.gps.energy.monoMeV` is required when type is 'Mono'.")
        return self


class SourceGpsConfig(StrictModel):
    """Explicit GPS command payload nested under source."""

    particle: str = Field(min_length=1)
    position: GpsPositionConfig
    angular: GpsAngularConfig = Field(default_factory=GpsAngularConfig)
    energy: GpsEnergyConfig


class SourceConfig(StrictModel):
    """Primary source block represented directly as GPS configuration."""

    gps: SourceGpsConfig


class LensConfig(StrictModel):
    """Individual optical lens descriptor.

    `zmxFile` references the optical model source while `primary` indicates
    which lens entry should be treated as the principal lens for downstream
    assumptions.
    """

    name: str
    primary: bool
    zmx_file: str = Field(alias="zmxFile")


class OpticalGeometry(StrictModel):
    """Optical envelope dimensions in millimeters."""

    entrance_diameter: float = Field(alias="entranceDiameter", gt=0)
    sensor_max_width: float = Field(alias="sensorMaxWidth", gt=0)


class SensitiveDetectorConfig(StrictModel):
    """Sensitive detector placement and sizing strategy.

    `diameterRule` is intentionally stored as a constrained expression-like
    string so command-generation code can resolve detector diameter
    deterministically from optical geometry values.
    """

    position_mm: Vec3Mm
    shape: str = Field(min_length=1)
    diameter_rule: str = Field(alias="diameterRule", min_length=1)


class OpticalConfig(StrictModel):
    """Optical subsystem definition.

    Includes:
    - lens list metadata
    - lens-derived envelope geometry
    - sensitive detector placement/rule configuration
    """

    lenses: list[LensConfig] = Field(min_length=1)
    geometry: OpticalGeometry
    sensitive_detector_config: SensitiveDetectorConfig = Field(
        alias="sensitiveDetectorConfig"
    )

    @model_validator(mode="after")
    def validate_primary_lens_count(self) -> "OpticalConfig":
        """Require exactly one primary lens designation.

        A single primary lens simplifies downstream assumptions in macro
        generation and geometry bookkeeping.
        """

        primary_count = sum(1 for lens in self.lenses if lens.primary)
        if primary_count != 1:
            raise ValueError("`optical.lenses` must contain exactly one primary lens.")
        return self


class OutputInfo(StrictModel):
    """Output block under metadata with YAML alias preservation.

    Aliases (`DataDirectory`, `LogDirectory`, `OutputFormat`) are kept to match
    user-facing YAML conventions while Python uses snake_case attributes.
    """

    data_directory: str = Field(alias="DataDirectory", min_length=1)
    log_directory: str = Field(alias="LogDirectory", min_length=1)
    output_format: str = Field(alias="OutputFormat", min_length=1)


class MetadataConfig(StrictModel):
    """Simulation metadata and IO context block."""

    author: str = Field(min_length=1)
    date: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    working_directory: str = Field(alias="WorkingDirectory", min_length=1)
    output_info: OutputInfo = Field(alias="OutputInfo")
    simulation_run_id: str = Field(alias="SimulationRunID", min_length=1)

    @field_validator("date", mode="before")
    @classmethod
    def normalize_yaml_date(cls, value: object) -> object:
        """Normalize YAML date-like scalars to canonical ISO strings.

        YAML parsers may decode unquoted dates into `date`/`datetime` objects.
        This validator converts those to ISO strings so the field stays a
        predictable textual representation.
        """

        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, DateType):
            return value.isoformat()
        return value


class RuntimeControlsConfig(StrictModel):
    """Optional GEANT4 runtime control command settings.

    These values map to macro preamble commands commonly used for run logging
    and progress control.
    """

    control_verbose: int | None = Field(default=None, alias="controlVerbose", ge=0)
    run_verbose: int | None = Field(default=None, alias="runVerbose", ge=0)
    event_verbose: int | None = Field(default=None, alias="eventVerbose", ge=0)
    tracking_verbose: int | None = Field(default=None, alias="trackingVerbose", ge=0)
    print_progress: int | None = Field(default=None, alias="printProgress", gt=0)
    store_trajectory: bool | None = Field(default=None, alias="storeTrajectory")

    @model_validator(mode="after")
    def require_at_least_one_control(self) -> "RuntimeControlsConfig":
        """Require at least one runtime control field when block is present."""

        if (
            self.control_verbose is None
            and self.run_verbose is None
            and self.event_verbose is None
            and self.tracking_verbose is None
            and self.print_progress is None
            and self.store_trajectory is None
        ):
            raise ValueError(
                "`simulation.runtimeControls` must set at least one control value."
            )
        return self


class SimulationConfig(StrictModel):
    """Run-control block for simulation execution commands.

    This block captures execution-time knobs that map to `/run/*` macro
    commands. It is intentionally separate from geometry and metadata so run
    volume can be tuned without changing detector/source definitions.
    """

    number_of_particles: int | None = Field(default=None, alias="numberOfParticles", gt=0)
    runtime_controls: RuntimeControlsConfig | None = Field(
        default=None, alias="runtimeControls"
    )

    @model_validator(mode="after")
    def require_at_least_one_setting(self) -> "SimulationConfig":
        """Require at least one run-control setting when block is present."""

        if self.number_of_particles is None and self.runtime_controls is None:
            raise ValueError(
                "`simulation` must include `numberOfParticles` and/or `runtimeControls`."
            )
        return self


class SimConfig(StrictModel):
    """Top-level simulation configuration root.

    The `metadata` field accepts either `metadata` or aliased `Metadata` in
    input YAML and serializes back out as `Metadata` for consistency with
    project examples.
    """

    scintillator: ScintillatorConfig
    source: SourceConfig
    optical: OpticalConfig
    simulation: SimulationConfig | None = None
    metadata: MetadataConfig = Field(
        validation_alias=AliasChoices("Metadata", "metadata"),
        serialization_alias="Metadata",
    )


def default_sim_config() -> SimConfig:
    """Return a minimal valid configuration for bootstrapping/tests.

    This function is intentionally explicit (rather than incremental mutation)
    so defaults are easy to inspect and copy into example YAML files.
    """

    return SimConfig.model_validate(
        {
            "scintillator": {
                "position_mm": {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0},
                "dimension_mm": {"x_mm": 50.0, "y_mm": 50.0, "z_mm": 10.0},
                "properties": {
                    "name": "EJ-200",
                    "photonEnergy": [2.8, 3.0, 3.2],
                    "rIndex": [1.58, 1.59, 1.60],
                    "nKEntries": 3,
                    "timeConstant": 2.1,
                },
            },
            "source": {
                "gps": {
                    "particle": "neutron",
                    "position": {
                        "type": "Plane",
                        "shape": "Circle",
                        "centerMm": {"x_mm": 0.0, "y_mm": 0.0, "z_mm": -20.0},
                        "radiusMm": 1.0,
                    },
                    "angular": {
                        "type": "beam2d",
                        "rot1": {"x": 1.0, "y": 0.0, "z": 0.0},
                        "rot2": {"x": 0.0, "y": 1.0, "z": 0.0},
                        "direction": {"x": 0.0, "y": 0.0, "z": 1.0},
                    },
                    "energy": {"type": "Mono", "monoMeV": 2.45},
                }
            },
            "optical": {
                "lenses": [
                    {
                        "name": "PrimaryLensOrMacro",
                        "primary": True,
                        "zmxFile": "primary.zmx",
                    }
                ],
                "geometry": {"entranceDiameter": 50.0, "sensorMaxWidth": 36.0},
                "sensitiveDetectorConfig": {
                    "position_mm": {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 25.0},
                    "shape": "circle",
                    "diameterRule": "min(entranceDiameter,sensorMaxWidth)",
                },
            },
            "simulation": {
                "numberOfParticles": 10000,
            },
            "Metadata": {
                "author": "Your Name",
                "date": "YEAR-MONTH-DAY",
                "version": "ScintPiX [VERSION]",
                "description": "Simulation configuration for scintillator and optical system.",
                "WorkingDirectory": "./",
                "OutputInfo": {
                    "DataDirectory": "output/",
                    "LogDirectory": "logs/",
                    "OutputFormat": "hdf5",
                },
                "SimulationRunID": "sim_001",
            },
        }
    )
