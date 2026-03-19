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
import math
from pathlib import Path
from typing import Literal
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


class ScintillationTimeComponent(StrictModel):
    """Single scintillation decay component in nanoseconds."""

    time_constant: float = Field(alias="timeConstant", ge=0)
    yield_fraction: float = Field(alias="yieldFraction", ge=0)


class ScintillationTimeComponentsByExcitation(StrictModel):
    """Particle-keyed scintillation component profiles.

    Supported optional profiles:
    - ``default``: generic fallback profile
    - ``neutron``: profile selected for neutron sources
    - ``gamma``: profile selected for gamma sources
    """

    default: list[ScintillationTimeComponent] | None = None
    neutron: list[ScintillationTimeComponent] | None = None
    gamma: list[ScintillationTimeComponent] | None = None

    @staticmethod
    def _validate_profile(
        profile_name: str,
        components: list[ScintillationTimeComponent],
    ) -> None:
        if len(components) != 3:
            raise ValueError(
                f"`timeComponents.{profile_name}` must define exactly 3 components."
            )
        total = sum(component.yield_fraction for component in components)
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1.0e-9):
            raise ValueError(
                f"`timeComponents.{profile_name}` yield fractions must sum to ~1.0."
            )
        active_component_count = sum(
            1
            for component in components
            if component.yield_fraction > 0.0 and component.time_constant > 0.0
        )
        if active_component_count == 0:
            raise ValueError(
                f"`timeComponents.{profile_name}` must define at least one active "
                "component (`yieldFraction > 0` and `timeConstant > 0`)."
            )

    @model_validator(mode="after")
    def validate_profiles(self) -> "ScintillationTimeComponentsByExcitation":
        """Require at least one profile and validate each present profile."""

        profile_names = ("default", "neutron", "gamma")
        present = False
        for profile_name in profile_names:
            components = getattr(self, profile_name)
            if components is None:
                continue
            present = True
            self._validate_profile(profile_name, components)
        if not present:
            raise ValueError(
                "`timeComponents` must provide at least one profile: "
                "`default`, `neutron`, or `gamma`."
            )
        return self

    def resolve_for_particle(
        self,
        particle: str,
    ) -> tuple[str, list[ScintillationTimeComponent]]:
        """Select profile for a source particle with fallback handling."""

        token = particle.strip().lower()
        if token in {"neutron", "n"} and self.neutron is not None:
            return "neutron", self.neutron
        if token in {"gamma", "g"} and self.gamma is not None:
            return "gamma", self.gamma
        if self.default is not None:
            return "default", self.default

        available_profiles = [
            profile_name
            for profile_name in ("neutron", "gamma")
            if getattr(self, profile_name) is not None
        ]
        if len(available_profiles) == 1:
            profile_name = available_profiles[0]
            components = getattr(self, profile_name)
            assert components is not None
            return profile_name, components

        raise ValueError(
            "Could not resolve scintillation `timeComponents` profile for "
            f"particle {particle!r}. Provide a matching profile "
            "(`neutron`/`gamma`) or `default`."
        )


class ScintillatorProperties(StrictModel):
    """Optical material table for scintillator definition.

    Fields map directly to common GEANT4 material-property table concepts.
    Core fields (`photonEnergy`, `rIndex`, `nKEntries`, `timeComponents`)
    define mandatory optical behavior, while extended fields enable full
    material and optical-table configuration through macros.
    """

    name: str
    photon_energy: list[float] = Field(alias="photonEnergy", min_length=1)
    r_index: list[float] = Field(alias="rIndex", min_length=1)
    n_k_entries: int = Field(alias="nKEntries", gt=0)
    time_components: ScintillationTimeComponentsByExcitation = Field(
        alias="timeComponents"
    )
    abs_length: list[float] | None = Field(default=None, alias="absLength")
    scint_spectrum: list[float] | None = Field(default=None, alias="scintSpectrum")
    density: float | None = Field(default=None, gt=0)
    carbon_atoms: int | None = Field(default=None, alias="carbonAtoms", gt=0)
    hydrogen_atoms: int | None = Field(default=None, alias="hydrogenAtoms", gt=0)
    scint_yield: float | None = Field(default=None, alias="scintYield", gt=0)
    resolution_scale: float | None = Field(default=None, alias="resolutionScale", gt=0)

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
        if self.abs_length is not None and len(self.abs_length) != self.n_k_entries:
            raise ValueError("`absLength` length must match `nKEntries`.")
        if (
            self.scint_spectrum is not None
            and len(self.scint_spectrum) != self.n_k_entries
        ):
            raise ValueError("`scintSpectrum` length must match `nKEntries`.")
        return self


class ScintillatorConfig(StrictModel):
    """Scintillator geometry + material properties block."""

    catalog_id: str | None = Field(default=None, alias="catalogId", min_length=1)
    position_mm: Vec3Mm
    dimension_mm: Size3Mm
    mask_radius_mm: float = Field(
        default=0.0,
        validation_alias=AliasChoices("maskRadius", "maskRadiusMm", "mask_radius_mm"),
        serialization_alias="maskRadius",
        ge=0,
    )
    properties: ScintillatorProperties | None = None

    @model_validator(mode="after")
    def require_properties_or_catalog(self) -> "ScintillatorConfig":
        """Require either explicit properties or a catalog reference."""

        if self.catalog_id is None and self.properties is None:
            raise ValueError(
                "`scintillator` must provide `properties` and/or `catalogId`."
            )
        return self


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

    A lens can be specified either directly with `zmxFile` (and optional
    `smxFile`) or via `catalogId` resolved from `lenses/catalog.yaml`.
    `primary` indicates which lens entry should be treated as the principal
    lens for downstream assumptions.
    """

    name: str | None = None
    primary: bool
    catalog_id: str | None = Field(default=None, alias="catalogId", min_length=1)
    zmx_file: str | None = Field(default=None, alias="zmxFile", min_length=1)
    smx_file: str | None = Field(default=None, alias="smxFile", min_length=1)

    @model_validator(mode="after")
    def validate_lens_reference(self) -> "LensConfig":
        """Require lens reference and fill a fallback display name."""

        if self.catalog_id is None and self.zmx_file is None:
            raise ValueError(
                "Each optical lens must provide `catalogId` and/or `zmxFile`."
            )
        if self.name is None or not self.name.strip():
            if self.catalog_id is not None:
                self.name = self.catalog_id
            elif self.zmx_file is not None:
                self.name = Path(self.zmx_file).stem
            else:
                self.name = "Lens"
        return self


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


class OpticalTransportAssumptionsConfig(StrictModel):
    """Physical mapping assumptions used by downstream optical transport.

    Definitions:
    - `objectPlane`: origin object plane for lens focus assumptions.
    - `opticalInterfaceRepresents`: physical meaning of Geant4 optical-interface
      hit plane used as ray-tracing input.
    """

    object_plane: Literal["scintillator_back_face"] = Field(
        default="scintillator_back_face",
        validation_alias=AliasChoices("objectPlane", "object_plane"),
        serialization_alias="objectPlane",
    )
    optical_interface_represents: Literal["lens_entrance_plane"] = Field(
        default="lens_entrance_plane",
        validation_alias=AliasChoices(
            "opticalInterfaceRepresents",
            "optical_interface_represents",
        ),
        serialization_alias="opticalInterfaceRepresents",
    )


class IntensifierInputScreenConfig(StrictModel):
    """Usable active area on the intensifier input plane."""

    image_circle_diameter_mm: float = Field(
        gt=0.0,
        validation_alias=AliasChoices(
            "image_circle_diameter_mm",
            "imageCircleDiameterMm",
        ),
        serialization_alias="image_circle_diameter_mm",
    )
    center_mm: tuple[float, float] = Field(
        default=(0.0, 0.0),
        validation_alias=AliasChoices("center_mm", "centerMm"),
        serialization_alias="center_mm",
    )
    magnification: float = Field(default=1.0, gt=0.0)
    coordinate_frame: str = Field(
        default="intensifier_input_plane",
        validation_alias=AliasChoices("coordinate_frame", "coordinateFrame"),
        serialization_alias="coordinate_frame",
        min_length=1,
    )
    notes: str | None = None

    @field_validator("center_mm", mode="before")
    @classmethod
    def normalize_center_mm(cls, value: object) -> tuple[float, float]:
        """Accept center as `[x, y]`, `(x, y)`, or `{x_mm, y_mm}`."""

        if value is None:
            return (0.0, 0.0)
        if isinstance(value, (tuple, list)):
            if len(value) != 2:
                raise ValueError("`center_mm` must contain exactly two values: [x_mm, y_mm].")
            return (float(value[0]), float(value[1]))
        if isinstance(value, dict):
            keys = set(value.keys())
            if {"x_mm", "y_mm"}.issubset(keys):
                return (float(value["x_mm"]), float(value["y_mm"]))
            if {"x", "y"}.issubset(keys):
                return (float(value["x"]), float(value["y"]))
        raise ValueError(
            "`center_mm` must be [x_mm, y_mm], [x, y], "
            "or a mapping with either `{x_mm, y_mm}` or `{x, y}`."
        )


class IntensifierConfig(StrictModel):
    """Image-intensifier model metadata and active input-screen definition."""

    class PhotocathodeStageConfig(StrictModel):
        """Photocathode response parameters for the intensifier model."""

        qe_wavelength_nm: list[float] = Field(
            default_factory=lambda: [350.0, 500.0, 650.0],
            validation_alias=AliasChoices("qe_wavelength_nm", "qeWavelengthNm"),
            serialization_alias="qe_wavelength_nm",
            min_length=1,
        )
        qe_values: list[float] = Field(
            default_factory=lambda: [0.15, 0.25, 0.05],
            validation_alias=AliasChoices("qe_values", "qeValues"),
            serialization_alias="qe_values",
            min_length=1,
        )
        collection_efficiency: float = Field(
            default=1.0,
            validation_alias=AliasChoices(
                "collection_efficiency",
                "collectionEfficiency",
            ),
            serialization_alias="collection_efficiency",
            ge=0.0,
            le=1.0,
        )
        tts_sigma_ns: float = Field(
            default=0.0,
            validation_alias=AliasChoices("tts_sigma_ns", "ttsSigmaNs"),
            serialization_alias="tts_sigma_ns",
            ge=0.0,
        )

        @model_validator(mode="after")
        def validate_qe_tables(self) -> "IntensifierConfig.PhotocathodeStageConfig":
            if len(self.qe_wavelength_nm) != len(self.qe_values):
                raise ValueError(
                    "`intensifier.photocathode.qe_wavelength_nm` and "
                    "`intensifier.photocathode.qe_values` must have the same length."
                )
            if any(
                later < earlier
                for earlier, later in zip(
                    self.qe_wavelength_nm,
                    self.qe_wavelength_nm[1:],
                )
            ):
                raise ValueError(
                    "`intensifier.photocathode.qe_wavelength_nm` must be monotonic increasing."
                )
            if any(value < 0.0 or value > 1.0 for value in self.qe_values):
                raise ValueError(
                    "`intensifier.photocathode.qe_values` must lie in [0, 1]."
                )
            return self

    class McpStageConfig(StrictModel):
        """Dual-stage MCP parameters for the intensifier model."""

        stage1_mean_gain: float = Field(
            default=8.0,
            validation_alias=AliasChoices("stage1_mean_gain", "stage1MeanGain"),
            serialization_alias="stage1_mean_gain",
            gt=0.0,
        )
        stage1_gain_shape: float = Field(
            default=2.0,
            validation_alias=AliasChoices("stage1_gain_shape", "stage1GainShape"),
            serialization_alias="stage1_gain_shape",
            gt=0.0,
        )
        stage2_mean_gain: float = Field(
            default=800.0,
            validation_alias=AliasChoices("stage2_mean_gain", "stage2MeanGain"),
            serialization_alias="stage2_mean_gain",
            gt=0.0,
        )
        stage2_gain_shape: float = Field(
            default=2.0,
            validation_alias=AliasChoices("stage2_gain_shape", "stage2GainShape"),
            serialization_alias="stage2_gain_shape",
            gt=0.0,
        )
        gain_ref: float = Field(
            default=1000.0,
            validation_alias=AliasChoices("gain_ref", "gainRef"),
            serialization_alias="gain_ref",
            gt=0.0,
        )
        spread_sigma0_mm: float = Field(
            default=0.03,
            validation_alias=AliasChoices("spread_sigma0_mm", "spreadSigma0Mm"),
            serialization_alias="spread_sigma0_mm",
            gt=0.0,
        )
        spread_gain_exponent: float = Field(
            default=0.4,
            validation_alias=AliasChoices(
                "spread_gain_exponent",
                "spreadGainExponent",
            ),
            serialization_alias="spread_gain_exponent",
        )

    class PhosphorStageConfig(StrictModel):
        """Phosphor response parameters for the intensifier model."""

        phosphor_gain: float = Field(
            default=1.0,
            validation_alias=AliasChoices("phosphor_gain", "phosphorGain"),
            serialization_alias="phosphor_gain",
            gt=0.0,
        )
        decay_fast_ns: float = Field(
            default=70.0,
            validation_alias=AliasChoices("decay_fast_ns", "decayFastNs"),
            serialization_alias="decay_fast_ns",
            ge=0.0,
        )
        decay_slow_ns: float = Field(
            default=200.0,
            validation_alias=AliasChoices("decay_slow_ns", "decaySlowNs"),
            serialization_alias="decay_slow_ns",
            ge=0.0,
        )
        fast_fraction: float = Field(
            default=0.9,
            validation_alias=AliasChoices("fast_fraction", "fastFraction"),
            serialization_alias="fast_fraction",
            ge=0.0,
            le=1.0,
        )
        psf_sigma_mm: float = Field(
            default=0.04,
            validation_alias=AliasChoices("psf_sigma_mm", "psfSigmaMm"),
            serialization_alias="psf_sigma_mm",
            ge=0.0,
        )

    model: str = Field(min_length=1)
    input_screen: IntensifierInputScreenConfig = Field(
        validation_alias=AliasChoices("input_screen", "inputScreen"),
        serialization_alias="input_screen",
    )
    photocathode: PhotocathodeStageConfig = Field(default_factory=PhotocathodeStageConfig)
    mcp: McpStageConfig = Field(default_factory=McpStageConfig)
    phosphor: PhosphorStageConfig = Field(default_factory=PhosphorStageConfig)


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
    show_transport_progress: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "showTransportProgress",
            "show_transport_progress",
        ),
        serialization_alias="showTransportProgress",
    )
    transport_assumptions: OpticalTransportAssumptionsConfig = Field(
        default_factory=OpticalTransportAssumptionsConfig,
        alias="transportAssumptions",
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


class RunEnvironmentOutputInfo(StrictModel):
    """Output staging settings nested under `RunEnvironment`.

    Directory values are interpreted relative to
    `Metadata.RunEnvironment.WorkingDirectory` when given as relative paths.

    Transport chunking controls apply to optical-transport HDF5 writing:
    - `transport_chunk_rows`:
      - integer: explicit rows per HDF5 chunk and per in-memory work batch.
      - `"auto"`: derive rows from `transport_chunk_target_mib`.
    - `transport_chunk_target_mib`:
      - target memory budget (MiB) for one transport processing batch when
        `transport_chunk_rows` is `"auto"`.
      - the transport module estimates rows using
        `(input_row_bytes + output_row_bytes)` and clamps to valid bounds.
    """

    simulated_photons_dir: str = Field(
        default="simulatedPhotons",
        validation_alias=AliasChoices(
            "SimulatedPhotonsDirectory",
            "simulated_photons_dir",
            "simulatedPhotonsDir",
        ),
        serialization_alias="SimulatedPhotonsDirectory",
        min_length=1,
    )
    transported_photons_dir: str = Field(
        default="transportedPhotons",
        validation_alias=AliasChoices(
            "TransportedPhotonsDirectory",
            "transported_photons_dir",
            "transportedPhotonsDir",
        ),
        serialization_alias="TransportedPhotonsDirectory",
        min_length=1,
    )
    transport_chunk_rows: int | Literal["auto"] = Field(
        default="auto",
        validation_alias=AliasChoices(
            "TransportChunkRows",
            "transport_chunk_rows",
            "transportChunkRows",
        ),
        serialization_alias="TransportChunkRows",
    )
    transport_chunk_target_mib: float = Field(
        default=32.0,
        validation_alias=AliasChoices(
            "TransportChunkTargetMiB",
            "transport_chunk_target_mib",
            "transportChunkTargetMiB",
        ),
        serialization_alias="TransportChunkTargetMiB",
        gt=0.0,
    )

    @field_validator("transport_chunk_rows", mode="before")
    @classmethod
    def normalize_transport_chunk_rows(
        cls,
        value: object,
    ) -> int | Literal["auto"]:
        """Normalize `TransportChunkRows` input into `int` or `"auto"`.

        Accepted inputs:
        - `None` or empty string -> `"auto"`
        - case-insensitive `"auto"` string -> `"auto"`
        - positive integer (or numeric string) -> integer row count

        Rejected inputs:
        - zero/negative values
        - non-numeric strings other than `"auto"`
        - non-string/non-integer object types
        """

        if value is None:
            return "auto"
        if isinstance(value, str):
            token = value.strip()
            if token == "":
                return "auto"
            if token.lower() == "auto":
                return "auto"
            try:
                value = int(token)
            except ValueError as exc:
                raise ValueError(
                    "`TransportChunkRows` must be a positive integer or 'auto'."
                ) from exc
        if isinstance(value, int):
            if value <= 0:
                raise ValueError("`TransportChunkRows` must be > 0 when specified.")
            return value
        raise ValueError("`TransportChunkRows` must be a positive integer or 'auto'.")


class RunEnvironmentConfig(StrictModel):
    """Run directory layout and execution-path context.

    Default layout policy:
    - `SimulationRunID`: "example"
    - `SubRunNumber`: `0`
    - `WorkingDirectory`: `data/`
    - `MacroDirectory`: `macros/`
    - `LogDirectory`: `logs/`
    - `OutputInfo.SimulatedPhotonsDirectory`: `simulatedPhotons/`
    - `OutputInfo.TransportedPhotonsDirectory`: `transportedPhotons/`
    - `OutputInfo.TransportChunkRows`: `auto`
    - `OutputInfo.TransportChunkTargetMiB`: `32`
    """

    simulation_run_id: str = Field(alias="SimulationRunID", default="example", min_length=1)
    sub_run_number: int = Field(alias="SubRunNumber", default=0, ge=0, le=9999)
    working_directory: str | None = Field(default=None, alias="WorkingDirectory")
    macro_directory: str | None = Field(default=None, alias="MacroDirectory")
    log_directory: str | None = Field(default=None, alias="LogDirectory")
    output_info: RunEnvironmentOutputInfo = Field(
        alias="OutputInfo", default_factory=RunEnvironmentOutputInfo
    )

    @model_validator(mode="after")
    def apply_layout_defaults(self) -> "RunEnvironmentConfig":
        """Fill directory defaults for run environment.

        WorkingDirectory defaults to `data`.
        Run-specific directories are resolved later as
        `<WorkingDirectory>/<SimulationRunID>/...`.
        """

        if self.working_directory is None or not self.working_directory.strip():
            self.working_directory = "data"
        if self.macro_directory is None or not self.macro_directory.strip():
            self.macro_directory = "macros"
        if self.log_directory is None or not self.log_directory.strip():
            self.log_directory = "logs"
        return self


class MetadataConfig(StrictModel):
    """Simulation metadata and IO context block."""

    author: str = Field(min_length=1)
    date: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    run_environment: RunEnvironmentConfig = Field(
        validation_alias=AliasChoices("RunEnvironment", "run_environment"),
        serialization_alias="RunEnvironment",
        default_factory=RunEnvironmentConfig,
    )

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


class RunnerConfig(StrictModel):
    """Python-side simulation launch settings consumed by `src.runner`.

    These values are intentionally separate from :class:`SimulationConfig`,
    which maps to GEANT4 macro commands. `RunnerConfig` captures how Python
    should launch and verify a simulation that has already been configured.
    The runner launches GEANT4 in batch mode via a macro file, so the default
    terminal progress bar is off unless explicitly enabled.
    """

    binary: str = Field(min_length=1, default="g4emi")
    show_progress: bool = Field(default=False, alias="showProgress")
    verify_output: bool = Field(default=True, alias="verifyOutput")

    @field_validator("binary")
    @classmethod
    def require_non_blank_binary(cls, value: str) -> str:
        """Reject blank/whitespace-only executable names."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("`runner.binary` must not be blank.")
        return normalized


class SimConfig(StrictModel):
    """Top-level simulation configuration root.

    The `metadata` field accepts either `metadata` or aliased `Metadata` in
    input YAML and serializes back out as `Metadata` for consistency with
    project examples.
    """

    scintillator: ScintillatorConfig
    source: SourceConfig
    optical: OpticalConfig
    intensifier: IntensifierConfig | None = None
    simulation: SimulationConfig | None = None
    runner: RunnerConfig = Field(default_factory=RunnerConfig)
    metadata: MetadataConfig = Field(
        validation_alias=AliasChoices("Metadata", "metadata"),
        serialization_alias="Metadata",
    )

    @model_validator(mode="after")
    def validate_scintillation_profile_selection(self) -> "SimConfig":
        """Ensure configured source particle has a resolvable time profile."""

        properties = self.scintillator.properties
        if properties is not None:
            properties.time_components.resolve_for_particle(self.source.gps.particle)
        return self


def default_sim_config() -> SimConfig:
    """Return a minimal valid configuration for bootstrapping/tests.

    This function is intentionally explicit (rather than incremental mutation)
    so defaults are easy to inspect and copy into example YAML files.
    """

    return SimConfig.model_validate(
        {
            "scintillator": {
                "catalogId": "EJ200",
                "position_mm": {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0},
                "dimension_mm": {"x_mm": 50.0, "y_mm": 50.0, "z_mm": 10.0},
                "properties": {
                    "name": "EJ200",
                    "photonEnergy": [2.00, 2.40, 2.76, 3.10, 3.50],
                    "rIndex": [1.58, 1.58, 1.58, 1.58, 1.58],
                    "absLength": [380.0, 380.0, 380.0, 300.0, 220.0],
                    "scintSpectrum": [0.05, 0.35, 1.00, 0.45, 0.08],
                    "nKEntries": 5,
                    "timeComponents": {
                        "default": [
                            {"timeConstant": 2.1, "yieldFraction": 1.0},
                            {"timeConstant": 0.0, "yieldFraction": 0.0},
                            {"timeConstant": 0.0, "yieldFraction": 0.0},
                        ]
                    },
                    "density": 1.023,
                    "carbonAtoms": 9,
                    "hydrogenAtoms": 10,
                    "scintYield": 10000.0,
                    "resolutionScale": 1.0,
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
                "showTransportProgress": True,
                "transportAssumptions": {
                    "objectPlane": "scintillator_back_face",
                    "opticalInterfaceRepresents": "lens_entrance_plane",
                },
            },
            "intensifier": {
                "model": "Cricket2",
                "input_screen": {
                    "image_circle_diameter_mm": 18.0,
                    "center_mm": [0.0, 0.0],
                    "magnification": 1.0,
                    "coordinate_frame": "intensifier_input_plane",
                    "notes": "Cricket2 nominal image-circle diameter and 1:1 magnification.",
                },
            },
            "simulation": {
                "numberOfParticles": 10000,
            },
            "runner": {
                "binary": "g4emi",
                "showProgress": True,
                "verifyOutput": True,
            },
            "Metadata": {
                "author": "Your Name",
                "date": "YEAR-MONTH-DAY",
                "version": "ScintPiX [VERSION]",
                "description": "Simulation configuration for scintillator and optical system.",
                "RunEnvironment": {
                    "SimulationRunID": "sim_001",
                    "WorkingDirectory": "data",
                    "MacroDirectory": "macros",
                    "LogDirectory": "logs",
                    "OutputInfo": {
                        "SimulatedPhotonsDirectory": "simulatedPhotons",
                        "TransportedPhotonsDirectory": "transportedPhotons",
                        "TransportChunkRows": "auto",
                        "TransportChunkTargetMiB": 32.0,
                    },
                },
            },
        }
    )
