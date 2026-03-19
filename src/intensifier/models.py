"""Internal parameter and event-batch models for the intensifier stage.

This module defines the in-memory contracts between the planned intensifier
submodules:

- `io.py` loads `TransportedPhotonBatch`
- `photocathode.py` emits `PhotoelectronBatch`
- `mcp.py` emits `McpEventBatch`
- `phosphor.py` emits `IntensifierOutputBatch`

These models are intentionally distinct from persisted HDF5 schema constants in
`src/common/hdf5_schema.py`. They describe internal pipeline data only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt


FloatArray = npt.NDArray[np.float64]
Int64Array = npt.NDArray[np.int64]
Int32Array = npt.NDArray[np.int32]


def _as_1d_array(values: Any, dtype: npt.DTypeLike, label: str) -> np.ndarray:
    """Return `values` as a 1D NumPy array with the requested dtype."""

    array = np.asarray(values, dtype=dtype)
    if array.ndim != 1:
        raise ValueError(f"`{label}` must be a 1D array.")
    return array


def _require_equal_lengths(owner: str, arrays: dict[str, np.ndarray]) -> int:
    """Validate that all arrays in one batch have the same length."""

    lengths = {name: int(array.shape[0]) for name, array in arrays.items()}
    unique_lengths = sorted(set(lengths.values()))
    if len(unique_lengths) != 1:
        details = ", ".join(f"{name}={length}" for name, length in lengths.items())
        raise ValueError(f"{owner} arrays must share one length; got {details}.")
    return unique_lengths[0]


@dataclass(frozen=True, slots=True)
class PhotocathodeParams:
    """Normalized photocathode parameters resolved from `SimConfig`."""

    qe_wavelength_nm: FloatArray
    qe_values: FloatArray
    collection_efficiency: float = 1.0
    tts_sigma_ns: float = 0.0

    def __post_init__(self) -> None:
        qe_wavelength_nm = _as_1d_array(
            self.qe_wavelength_nm,
            np.float64,
            "qe_wavelength_nm",
        )
        qe_values = _as_1d_array(self.qe_values, np.float64, "qe_values")
        if qe_wavelength_nm.size == 0:
            raise ValueError("`qe_wavelength_nm` must not be empty.")
        if qe_wavelength_nm.size != qe_values.size:
            raise ValueError(
                "`qe_wavelength_nm` and `qe_values` must have the same length."
            )
        if np.any(np.diff(qe_wavelength_nm) < 0.0):
            raise ValueError("`qe_wavelength_nm` must be monotonic increasing.")
        if not 0.0 <= float(self.collection_efficiency) <= 1.0:
            raise ValueError("`collection_efficiency` must be in [0, 1].")
        if float(self.tts_sigma_ns) < 0.0:
            raise ValueError("`tts_sigma_ns` must be non-negative.")
        if np.any((qe_values < 0.0) | (qe_values > 1.0)):
            raise ValueError("`qe_values` must lie in [0, 1].")
        object.__setattr__(self, "qe_wavelength_nm", qe_wavelength_nm)
        object.__setattr__(self, "qe_values", qe_values)


@dataclass(frozen=True, slots=True)
class McpParams:
    """Normalized dual-stage MCP parameters resolved from `SimConfig`."""

    stage1_mean_gain: float
    stage1_gain_shape: float
    stage2_mean_gain: float
    stage2_gain_shape: float
    gain_ref: float
    spread_sigma0_mm: float
    spread_gain_exponent: float

    def __post_init__(self) -> None:
        for field_name in (
            "stage1_mean_gain",
            "stage1_gain_shape",
            "stage2_mean_gain",
            "stage2_gain_shape",
            "gain_ref",
        ):
            if float(getattr(self, field_name)) <= 0.0:
                raise ValueError(f"`{field_name}` must be strictly positive.")
        if float(self.spread_sigma0_mm) < 0.0:
            raise ValueError("`spread_sigma0_mm` must be non-negative.")


@dataclass(frozen=True, slots=True)
class PhosphorParams:
    """Normalized phosphor parameters resolved from `SimConfig`."""

    phosphor_gain: float
    decay_fast_ns: float
    decay_slow_ns: float
    fast_fraction: float
    psf_sigma_mm: float

    def __post_init__(self) -> None:
        if float(self.phosphor_gain) <= 0.0:
            raise ValueError("`phosphor_gain` must be strictly positive.")
        if float(self.decay_fast_ns) < 0.0:
            raise ValueError("`decay_fast_ns` must be non-negative.")
        if float(self.decay_slow_ns) < 0.0:
            raise ValueError("`decay_slow_ns` must be non-negative.")
        if not 0.0 <= float(self.fast_fraction) <= 1.0:
            raise ValueError("`fast_fraction` must be in [0, 1].")
        if float(self.psf_sigma_mm) < 0.0:
            raise ValueError("`psf_sigma_mm` must be non-negative.")


@dataclass(frozen=True, slots=True)
class IntensifierParams:
    """Full stage parameter bundle passed through the intensifier pipeline."""

    photocathode: PhotocathodeParams
    mcp: McpParams
    phosphor: PhosphorParams


@dataclass(slots=True)
class TransportedPhotonBatch:
    """Optical-transport output rows normalized for intensifier input."""

    source_photon_index: Int64Array
    gun_call_id: Int64Array
    primary_track_id: Int32Array
    secondary_track_id: Int32Array
    photon_track_id: Int32Array
    x_mm: FloatArray
    y_mm: FloatArray
    z_mm: FloatArray
    time_ns: FloatArray
    wavelength_nm: FloatArray

    def __post_init__(self) -> None:
        self.source_photon_index = _as_1d_array(
            self.source_photon_index,
            np.int64,
            "source_photon_index",
        )
        self.gun_call_id = _as_1d_array(self.gun_call_id, np.int64, "gun_call_id")
        self.primary_track_id = _as_1d_array(
            self.primary_track_id,
            np.int32,
            "primary_track_id",
        )
        self.secondary_track_id = _as_1d_array(
            self.secondary_track_id,
            np.int32,
            "secondary_track_id",
        )
        self.photon_track_id = _as_1d_array(
            self.photon_track_id,
            np.int32,
            "photon_track_id",
        )
        self.x_mm = _as_1d_array(self.x_mm, np.float64, "x_mm")
        self.y_mm = _as_1d_array(self.y_mm, np.float64, "y_mm")
        self.z_mm = _as_1d_array(self.z_mm, np.float64, "z_mm")
        self.time_ns = _as_1d_array(self.time_ns, np.float64, "time_ns")
        self.wavelength_nm = _as_1d_array(
            self.wavelength_nm,
            np.float64,
            "wavelength_nm",
        )
        _require_equal_lengths(
            type(self).__name__,
            {
                "source_photon_index": self.source_photon_index,
                "gun_call_id": self.gun_call_id,
                "primary_track_id": self.primary_track_id,
                "secondary_track_id": self.secondary_track_id,
                "photon_track_id": self.photon_track_id,
                "x_mm": self.x_mm,
                "y_mm": self.y_mm,
                "z_mm": self.z_mm,
                "time_ns": self.time_ns,
                "wavelength_nm": self.wavelength_nm,
            },
        )

    def __len__(self) -> int:
        return int(self.source_photon_index.shape[0])


@dataclass(slots=True)
class PhotoelectronBatch:
    """Photocathode output events for the dual-stage MCP model."""

    source_photon_index: Int64Array
    gun_call_id: Int64Array
    primary_track_id: Int32Array
    secondary_track_id: Int32Array
    photon_track_id: Int32Array
    x_pc_mm: FloatArray
    y_pc_mm: FloatArray
    time_pc_ns: FloatArray
    wavelength_nm: FloatArray

    def __post_init__(self) -> None:
        self.source_photon_index = _as_1d_array(
            self.source_photon_index,
            np.int64,
            "source_photon_index",
        )
        self.gun_call_id = _as_1d_array(self.gun_call_id, np.int64, "gun_call_id")
        self.primary_track_id = _as_1d_array(
            self.primary_track_id,
            np.int32,
            "primary_track_id",
        )
        self.secondary_track_id = _as_1d_array(
            self.secondary_track_id,
            np.int32,
            "secondary_track_id",
        )
        self.photon_track_id = _as_1d_array(
            self.photon_track_id,
            np.int32,
            "photon_track_id",
        )
        self.x_pc_mm = _as_1d_array(self.x_pc_mm, np.float64, "x_pc_mm")
        self.y_pc_mm = _as_1d_array(self.y_pc_mm, np.float64, "y_pc_mm")
        self.time_pc_ns = _as_1d_array(self.time_pc_ns, np.float64, "time_pc_ns")
        self.wavelength_nm = _as_1d_array(
            self.wavelength_nm,
            np.float64,
            "wavelength_nm",
        )
        _require_equal_lengths(
            type(self).__name__,
            {
                "source_photon_index": self.source_photon_index,
                "gun_call_id": self.gun_call_id,
                "primary_track_id": self.primary_track_id,
                "secondary_track_id": self.secondary_track_id,
                "photon_track_id": self.photon_track_id,
                "x_pc_mm": self.x_pc_mm,
                "y_pc_mm": self.y_pc_mm,
                "time_pc_ns": self.time_pc_ns,
                "wavelength_nm": self.wavelength_nm,
            },
        )

    def __len__(self) -> int:
        return int(self.source_photon_index.shape[0])


@dataclass(slots=True)
class McpEventBatch:
    """Dual-stage MCP output events before phosphor response."""

    source_photon_index: Int64Array
    gun_call_id: Int64Array
    primary_track_id: Int32Array
    secondary_track_id: Int32Array
    photon_track_id: Int32Array
    x_mcp_mm: FloatArray
    y_mcp_mm: FloatArray
    time_mcp_ns: FloatArray
    stage1_gain: FloatArray
    stage2_gain: FloatArray
    total_gain: FloatArray
    wavelength_nm: FloatArray

    def __post_init__(self) -> None:
        self.source_photon_index = _as_1d_array(
            self.source_photon_index,
            np.int64,
            "source_photon_index",
        )
        self.gun_call_id = _as_1d_array(self.gun_call_id, np.int64, "gun_call_id")
        self.primary_track_id = _as_1d_array(
            self.primary_track_id,
            np.int32,
            "primary_track_id",
        )
        self.secondary_track_id = _as_1d_array(
            self.secondary_track_id,
            np.int32,
            "secondary_track_id",
        )
        self.photon_track_id = _as_1d_array(
            self.photon_track_id,
            np.int32,
            "photon_track_id",
        )
        self.x_mcp_mm = _as_1d_array(self.x_mcp_mm, np.float64, "x_mcp_mm")
        self.y_mcp_mm = _as_1d_array(self.y_mcp_mm, np.float64, "y_mcp_mm")
        self.time_mcp_ns = _as_1d_array(self.time_mcp_ns, np.float64, "time_mcp_ns")
        self.stage1_gain = _as_1d_array(self.stage1_gain, np.float64, "stage1_gain")
        self.stage2_gain = _as_1d_array(self.stage2_gain, np.float64, "stage2_gain")
        self.total_gain = _as_1d_array(self.total_gain, np.float64, "total_gain")
        self.wavelength_nm = _as_1d_array(
            self.wavelength_nm,
            np.float64,
            "wavelength_nm",
        )
        _require_equal_lengths(
            type(self).__name__,
            {
                "source_photon_index": self.source_photon_index,
                "gun_call_id": self.gun_call_id,
                "primary_track_id": self.primary_track_id,
                "secondary_track_id": self.secondary_track_id,
                "photon_track_id": self.photon_track_id,
                "x_mcp_mm": self.x_mcp_mm,
                "y_mcp_mm": self.y_mcp_mm,
                "time_mcp_ns": self.time_mcp_ns,
                "stage1_gain": self.stage1_gain,
                "stage2_gain": self.stage2_gain,
                "total_gain": self.total_gain,
                "wavelength_nm": self.wavelength_nm,
            },
        )

    def __len__(self) -> int:
        return int(self.source_photon_index.shape[0])


@dataclass(slots=True)
class IntensifierOutputBatch:
    """Final in-memory intensifier output events before any future sensor stage."""

    source_photon_index: Int64Array
    gun_call_id: Int64Array
    primary_track_id: Int32Array
    secondary_track_id: Int32Array
    photon_track_id: Int32Array
    output_x_mm: FloatArray
    output_y_mm: FloatArray
    output_time_ns: FloatArray
    signal_amplitude_arb: FloatArray
    total_gain: FloatArray
    wavelength_nm: FloatArray

    def __post_init__(self) -> None:
        self.source_photon_index = _as_1d_array(
            self.source_photon_index,
            np.int64,
            "source_photon_index",
        )
        self.gun_call_id = _as_1d_array(self.gun_call_id, np.int64, "gun_call_id")
        self.primary_track_id = _as_1d_array(
            self.primary_track_id,
            np.int32,
            "primary_track_id",
        )
        self.secondary_track_id = _as_1d_array(
            self.secondary_track_id,
            np.int32,
            "secondary_track_id",
        )
        self.photon_track_id = _as_1d_array(
            self.photon_track_id,
            np.int32,
            "photon_track_id",
        )
        self.output_x_mm = _as_1d_array(self.output_x_mm, np.float64, "output_x_mm")
        self.output_y_mm = _as_1d_array(self.output_y_mm, np.float64, "output_y_mm")
        self.output_time_ns = _as_1d_array(
            self.output_time_ns,
            np.float64,
            "output_time_ns",
        )
        self.signal_amplitude_arb = _as_1d_array(
            self.signal_amplitude_arb,
            np.float64,
            "signal_amplitude_arb",
        )
        self.total_gain = _as_1d_array(self.total_gain, np.float64, "total_gain")
        self.wavelength_nm = _as_1d_array(
            self.wavelength_nm,
            np.float64,
            "wavelength_nm",
        )
        _require_equal_lengths(
            type(self).__name__,
            {
                "source_photon_index": self.source_photon_index,
                "gun_call_id": self.gun_call_id,
                "primary_track_id": self.primary_track_id,
                "secondary_track_id": self.secondary_track_id,
                "photon_track_id": self.photon_track_id,
                "output_x_mm": self.output_x_mm,
                "output_y_mm": self.output_y_mm,
                "output_time_ns": self.output_time_ns,
                "signal_amplitude_arb": self.signal_amplitude_arb,
                "total_gain": self.total_gain,
                "wavelength_nm": self.wavelength_nm,
            },
        )

    def __len__(self) -> int:
        return int(self.source_photon_index.shape[0])
