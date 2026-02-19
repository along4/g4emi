"""Hierarchical Pydantic models for GEANT4 simulation configuration.

The model tree is designed to match YAML structure directly while keeping
Python attribute names clean and type-safe.
"""

from __future__ import annotations

from enum import Enum

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Shared strict defaults across all config models."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
    )


class Vec3Mm(StrictModel):
    """3D vector in millimeters."""

    x_mm: float
    y_mm: float
    z_mm: float


class Size3Mm(StrictModel):
    """3D extents in millimeters; each component must be positive."""

    x_mm: float = Field(gt=0)
    y_mm: float = Field(gt=0)
    z_mm: float = Field(gt=0)


class ScintillatorProperties(StrictModel):
    """Optical material properties for scintillator definition."""

    name: str
    photon_energy: list[float] = Field(alias="photonEnergy", min_length=1)
    r_index: list[float] = Field(alias="rIndex", min_length=1)
    n_k_entries: int = Field(alias="nKEntries", gt=0)
    time_constant: float = Field(alias="timeConstant", gt=0)

    @model_validator(mode="after")
    def validate_table_lengths(self) -> "ScintillatorProperties":
        """Require energy/refractive-index table lengths to match nKEntries."""

        if len(self.photon_energy) != self.n_k_entries:
            raise ValueError("`photonEnergy` length must match `nKEntries`.")
        if len(self.r_index) != self.n_k_entries:
            raise ValueError("`rIndex` length must match `nKEntries`.")
        return self


class ScintillatorConfig(StrictModel):
    """Scintillator block configuration."""

    position_mm: Vec3Mm
    dimension_mm: Size3Mm
    properties: ScintillatorProperties


class EnergyType(str, Enum):
    """Supported source energy specification modes."""

    monoenergetic = "monoenergetic"
    spectrum = "spectrum"
    distribution = "distribution"


class EnergyInfo(StrictModel):
    """Source energy configuration."""

    type: EnergyType
    value: float = Field(gt=0)


class Species(str, Enum):
    """Common GPS species values used in the simulation pipeline."""

    neutron = "neutron"
    photon = "photon"
    alpha = "alpha"


class SourceConfig(StrictModel):
    """Source geometry + particle/energy configuration."""

    position_mm: Vec3Mm
    dimension_mm: Size3Mm
    energy_info: EnergyInfo = Field(alias="energyInfo")
    species: Species | str = Field(min_length=1)


class LensConfig(StrictModel):
    """Individual optical lens descriptor."""

    name: str
    primary: bool
    zmx_file: str = Field(alias="zmxFile")


class OpticalGeometry(StrictModel):
    """Lens-driven optical geometry envelope values (mm)."""

    entrance_diameter: float = Field(alias="entranceDiameter", gt=0)
    sensor_max_width: float = Field(alias="sensorMaxWidth", gt=0)


class SensitiveDetectorConfig(StrictModel):
    """Sensitive detector placement + sizing rule."""

    position_mm: Vec3Mm
    shape: str = Field(min_length=1)
    diameter_rule: str = Field(alias="diameterRule", min_length=1)


class OpticalConfig(StrictModel):
    """Optical subsystem configuration."""

    lenses: list[LensConfig] = Field(min_length=1)
    geometry: OpticalGeometry
    sensitive_detector_config: SensitiveDetectorConfig = Field(
        alias="sensitiveDetectorConfig"
    )

    @model_validator(mode="after")
    def validate_primary_lens_count(self) -> "OpticalConfig":
        """Require exactly one primary lens entry in the list."""

        primary_count = sum(1 for lens in self.lenses if lens.primary)
        if primary_count != 1:
            raise ValueError("`optical.lenses` must contain exactly one primary lens.")
        return self


class OutputInfo(StrictModel):
    """Output settings with key aliases preserved from YAML."""

    data_directory: str = Field(alias="DataDirectory", min_length=1)
    log_directory: str = Field(alias="LogDirectory", min_length=1)
    output_format: str = Field(alias="OutputFormat", min_length=1)


class MetadataConfig(StrictModel):
    """Simulation metadata block."""

    author: str = Field(min_length=1)
    date: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    working_directory: str = Field(alias="WorkingDirectory", min_length=1)
    output_info: OutputInfo = Field(alias="OutputInfo")
    simulation_run_id: str = Field(alias="SimulationRunID", min_length=1)


class SimConfig(StrictModel):
    """Top-level simulation configuration matching YAML hierarchy."""

    scintillator: ScintillatorConfig
    source: SourceConfig
    optical: OpticalConfig
    metadata: MetadataConfig = Field(
        validation_alias=AliasChoices("Metadata", "metadata"),
        serialization_alias="Metadata",
    )


def default_sim_config() -> SimConfig:
    """Return a small valid default config for bootstrapping."""

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
                "position_mm": {"x_mm": 0.0, "y_mm": 0.0, "z_mm": -20.0},
                "dimension_mm": {"x_mm": 1.0, "y_mm": 1.0, "z_mm": 1.0},
                "energyInfo": {"type": "monoenergetic", "value": 2.45},
                "species": "neutron",
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
            "Metadata": {
                "author": "Your Name",
                "date": "YEAR-MONTH-DAY",
                "version": "ScintPiX [VERSION]",
                "description": "Simulation configuration for scintillator and optical system.",
                "WorkingDirectory": "/path/to/working/directory",
                "OutputInfo": {
                    "DataDirectory": "/path/to/data/directory",
                    "LogDirectory": "/path/to/log/directory",
                    "OutputFormat": "hdf5",
                },
                "SimulationRunID": "sim_001",
            },
        }
    )
