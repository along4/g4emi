"""Internal parameter and event-batch models for the sensor stage.

This module defines the in-memory contracts for the planned sensor/readout
submodules:

- `timepix.py` resolves normalized `TimepixParams` from `SimConfig`
- `timepix.py` maps intensifier output into `TimepixEventBatch`
- later sensor pipeline code will merge those into `TimepixHitBatch`

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
class TimepixParams:
    """Normalized Timepix geometry and readout settings resolved from `SimConfig`."""

    pixels_x: int
    pixels_y: int
    pixel_pitch_mm: float
    max_tot_ns: float
    dead_time_ns: float

    def __post_init__(self) -> None:
        if int(self.pixels_x) <= 0:
            raise ValueError("`pixels_x` must be strictly positive.")
        if int(self.pixels_y) <= 0:
            raise ValueError("`pixels_y` must be strictly positive.")
        if float(self.pixel_pitch_mm) <= 0.0:
            raise ValueError("`pixel_pitch_mm` must be strictly positive.")
        if float(self.max_tot_ns) <= 0.0:
            raise ValueError("`max_tot_ns` must be strictly positive.")
        if float(self.dead_time_ns) < 0.0:
            raise ValueError("`dead_time_ns` must be non-negative.")

    @property
    def sensor_width_mm(self) -> float:
        """Return active sensor width in millimeters."""

        return float(self.pixels_x) * float(self.pixel_pitch_mm)

    @property
    def sensor_height_mm(self) -> float:
        """Return active sensor height in millimeters."""

        return float(self.pixels_y) * float(self.pixel_pitch_mm)


@dataclass(slots=True)
class TimepixEventBatch:
    """Mapped per-event Timepix candidates before readout merging."""

    source_photon_index: Int64Array
    gun_call_id: Int64Array
    primary_track_id: Int32Array
    secondary_track_id: Int32Array
    photon_track_id: Int32Array
    x_pixel: Int32Array
    y_pixel: Int32Array
    event_time_ns: FloatArray
    signal_amplitude_arb: FloatArray

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
        self.x_pixel = _as_1d_array(self.x_pixel, np.int32, "x_pixel")
        self.y_pixel = _as_1d_array(self.y_pixel, np.int32, "y_pixel")
        self.event_time_ns = _as_1d_array(self.event_time_ns, np.float64, "event_time_ns")
        self.signal_amplitude_arb = _as_1d_array(
            self.signal_amplitude_arb,
            np.float64,
            "signal_amplitude_arb",
        )
        _require_equal_lengths(
            type(self).__name__,
            {
                "source_photon_index": self.source_photon_index,
                "gun_call_id": self.gun_call_id,
                "primary_track_id": self.primary_track_id,
                "secondary_track_id": self.secondary_track_id,
                "photon_track_id": self.photon_track_id,
                "x_pixel": self.x_pixel,
                "y_pixel": self.y_pixel,
                "event_time_ns": self.event_time_ns,
                "signal_amplitude_arb": self.signal_amplitude_arb,
            },
        )

    def __len__(self) -> int:
        return int(self.source_photon_index.shape[0])

    @classmethod
    def empty(cls) -> "TimepixEventBatch":
        """Return an empty mapped-event batch with the correct dtypes."""

        return cls(
            source_photon_index=np.array([], dtype=np.int64),
            gun_call_id=np.array([], dtype=np.int64),
            primary_track_id=np.array([], dtype=np.int32),
            secondary_track_id=np.array([], dtype=np.int32),
            photon_track_id=np.array([], dtype=np.int32),
            x_pixel=np.array([], dtype=np.int32),
            y_pixel=np.array([], dtype=np.int32),
            event_time_ns=np.array([], dtype=np.float64),
            signal_amplitude_arb=np.array([], dtype=np.float64),
        )


@dataclass(slots=True)
class TimepixHitBatch:
    """Final in-memory Timepix pixel-hit rows emitted by the sensor stage."""

    gun_call_id: Int64Array
    primary_track_id: Int32Array
    secondary_track_id: Int32Array
    x_pixel: Int32Array
    y_pixel: Int32Array
    time_of_arrival_ns: FloatArray
    time_over_threshold_ns: FloatArray
    contribution_count: Int32Array

    def __post_init__(self) -> None:
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
        self.x_pixel = _as_1d_array(self.x_pixel, np.int32, "x_pixel")
        self.y_pixel = _as_1d_array(self.y_pixel, np.int32, "y_pixel")
        self.time_of_arrival_ns = _as_1d_array(
            self.time_of_arrival_ns,
            np.float64,
            "time_of_arrival_ns",
        )
        self.time_over_threshold_ns = _as_1d_array(
            self.time_over_threshold_ns,
            np.float64,
            "time_over_threshold_ns",
        )
        self.contribution_count = _as_1d_array(
            self.contribution_count,
            np.int32,
            "contribution_count",
        )
        _require_equal_lengths(
            type(self).__name__,
            {
                "gun_call_id": self.gun_call_id,
                "primary_track_id": self.primary_track_id,
                "secondary_track_id": self.secondary_track_id,
                "x_pixel": self.x_pixel,
                "y_pixel": self.y_pixel,
                "time_of_arrival_ns": self.time_of_arrival_ns,
                "time_over_threshold_ns": self.time_over_threshold_ns,
                "contribution_count": self.contribution_count,
            },
        )

    def __len__(self) -> int:
        return int(self.gun_call_id.shape[0])

    @classmethod
    def empty(cls) -> "TimepixHitBatch":
        """Return an empty Timepix hit batch with the correct dtypes."""

        return cls(
            gun_call_id=np.array([], dtype=np.int64),
            primary_track_id=np.array([], dtype=np.int32),
            secondary_track_id=np.array([], dtype=np.int32),
            x_pixel=np.array([], dtype=np.int32),
            y_pixel=np.array([], dtype=np.int32),
            time_of_arrival_ns=np.array([], dtype=np.float64),
            time_over_threshold_ns=np.array([], dtype=np.float64),
            contribution_count=np.array([], dtype=np.int32),
        )
