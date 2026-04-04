"""HDF5 I/O helpers for the Timepix sensor stage."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

try:
    import h5py
except ModuleNotFoundError as exc:  # pragma: no cover - dependency availability varies
    raise ModuleNotFoundError(
        "h5py is required for sensor HDF5 I/O. "
        "Install project dependencies (for example: pixi install)."
    ) from exc
import numpy as np

from src.common.hdf5_schema import DATASET_TIMEPIX_HITS
from src.common.hdf5_schema import DATASET_PRIMARIES
from src.common.hdf5_schema import DATASET_SECONDARIES
from src.common.hdf5_schema import TIMEPIX_HIT_FIELDS
from src.config.ConfigIO import artifact_stem_for_sub_run
from src.config.ConfigIO import resolve_run_environment_paths
from src.intensifier.io import _copy_dataset_if_present
from src.intensifier.io import resolve_intensifier_input_hdf5_paths
from src.sensor.models import TimepixHitBatch

if TYPE_CHECKING:
    from src.config.SimConfig import SimConfig


_TIMEPIX_HIT_DTYPE = np.dtype(
    list(
        zip(
            TIMEPIX_HIT_FIELDS,
            (
                np.int64,
                np.int32,
                np.int32,
                np.int32,
                np.int32,
                np.float64,
                np.float64,
                np.int32,
            ),
            strict=True,
        )
    )
)


def timepix_hits_hdf5_path_from_sim_config(config: SimConfig) -> Path:
    """Return the default Timepix HDF5 path under `run_root/sensor/`."""

    run_paths = resolve_run_environment_paths(config)
    sensor_dir = (run_paths.run_root / "sensor").resolve()
    sub_run_number = config.metadata.run_environment.sub_run_number
    filename = f"{artifact_stem_for_sub_run('timepix_hits', sub_run_number)}.h5"
    return (sensor_dir / filename).resolve()


def _resolve_timepix_hits_hdf5_path(
    config: SimConfig,
    output_hdf5_path: str | Path | None,
) -> Path:
    """Resolve an explicit or config-derived Timepix output HDF5 path."""

    if output_hdf5_path is not None:
        return Path(output_hdf5_path).resolve()
    return timepix_hits_hdf5_path_from_sim_config(config)


def timepix_hit_batch_to_structured_array(
    hits: TimepixHitBatch,
) -> np.ndarray:
    """Convert one Timepix hit batch into the canonical HDF5 dtype."""

    structured = np.empty(len(hits), dtype=_TIMEPIX_HIT_DTYPE)
    structured["gun_call_id"] = hits.gun_call_id
    structured["primary_track_id"] = hits.primary_track_id
    structured["secondary_track_id"] = hits.secondary_track_id
    structured["x_pixel"] = hits.x_pixel
    structured["y_pixel"] = hits.y_pixel
    structured["time_of_arrival_ns"] = hits.time_of_arrival_ns
    structured["time_over_threshold_ns"] = hits.time_over_threshold_ns
    structured["contribution_count"] = hits.contribution_count
    return structured


def write_timepix_hits_hdf5(
    hits: TimepixHitBatch,
    *,
    config: SimConfig,
    transport_hdf5_path: str | Path | None = None,
    source_hdf5_path: str | Path | None = None,
    output_hdf5_path: str | Path | None = None,
) -> Path:
    """Write Timepix hit rows to a standalone HDF5 file."""

    transport_path, source_path = resolve_intensifier_input_hdf5_paths(
        config,
        transport_hdf5_path=transport_hdf5_path,
        source_hdf5_path=source_hdf5_path,
    )
    output_path = _resolve_timepix_hits_hdf5_path(config, output_hdf5_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    structured = timepix_hit_batch_to_structured_array(hits)
    intensifier = config.intensifier
    sensor = config.sensor
    if intensifier is None:
        raise ValueError("`config.intensifier` is required to write Timepix output.")
    if sensor is None:
        raise ValueError("`config.sensor` is required to write Timepix output.")

    with h5py.File(transport_path, "r") as transport_handle, h5py.File(
        output_path,
        "w",
    ) as output_handle:
        _copy_dataset_if_present(transport_handle, output_handle, DATASET_PRIMARIES)
        _copy_dataset_if_present(transport_handle, output_handle, DATASET_SECONDARIES)
        output_handle.create_dataset(DATASET_TIMEPIX_HITS, data=structured)

        output_handle.attrs["source_hdf5"] = str(source_path)
        output_handle.attrs["transport_hdf5"] = str(transport_path)
        output_handle.attrs["run_id"] = config.metadata.run_environment.simulation_run_id
        output_handle.attrs["intensifier_model"] = intensifier.model
        output_handle.attrs["sensor_model"] = sensor.model
        output_handle.attrs["generated_utc"] = datetime.now(timezone.utc).isoformat()

    return output_path
