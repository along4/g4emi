"""HDF5 I/O helpers for the intensifier stage."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import TYPE_CHECKING

try:
    import h5py
except ModuleNotFoundError as exc:  # pragma: no cover - dependency availability varies
    raise ModuleNotFoundError(
        "h5py is required for intensifier HDF5 I/O. "
        "Install project dependencies (for example: pixi install)."
    ) from exc
import numpy as np

from src.common.hdf5_schema import DATASET_INTENSIFIER_OUTPUT_EVENTS
from src.common.hdf5_schema import DATASET_PHOTONS
from src.common.hdf5_schema import DATASET_PRIMARIES
from src.common.hdf5_schema import DATASET_SECONDARIES
from src.common.hdf5_schema import DATASET_TRANSPORTED_PHOTONS
from src.common.logger import get_logger
from src.config.ConfigIO import artifact_stem_for_sub_run
from src.config.ConfigIO import resolve_run_environment_paths
from src.intensifier.models import IntensifierOutputBatch
from src.intensifier.models import TransportedPhotonBatch
from src.optics.OpticalTransport import resolve_transport_paths

if TYPE_CHECKING:
    from src.config.SimConfig import SimConfig

_REQUIRED_TRANSPORT_FIELDS = (
    "source_photon_index",
    "gun_call_id",
    "primary_track_id",
    "secondary_track_id",
    "photon_track_id",
    "intensifier_hit_x_mm",
    "intensifier_hit_y_mm",
    "intensifier_hit_z_mm",
    "intensifier_hit_time_ns",
    "intensifier_hit_wavelength_nm",
    "in_bounds",
)

_INTENSIFIER_OUTPUT_DTYPE = np.dtype(
    [
        ("source_photon_index", np.int64),
        ("gun_call_id", np.int64),
        ("primary_track_id", np.int32),
        ("secondary_track_id", np.int32),
        ("photon_track_id", np.int32),
        ("output_x_mm", np.float64),
        ("output_y_mm", np.float64),
        ("output_time_ns", np.float64),
        ("signal_amplitude_arb", np.float64),
        ("total_gain", np.float64),
        ("wavelength_nm", np.float64),
    ]
)
_DEFAULT_LOAD_CHUNK_ROWS = 250_000


def _require_fields(
    dataset_name: str,
    field_names: tuple[str, ...] | list[str],
    required_fields: tuple[str, ...],
) -> None:
    """Raise if any expected structured-array fields are missing."""

    available = set(field_names)
    missing = [field for field in required_fields if field not in available]
    if missing:
        raise KeyError(f"Dataset '{dataset_name}' is missing required fields: {missing}")


def _copy_dataset_if_present(
    source: h5py.File,
    destination: h5py.File,
    dataset_name: str,
) -> None:
    """Copy one dataset when present in the source HDF5 file."""

    if dataset_name in source:
        source.copy(dataset_name, destination)


def _require_existing_path(path: str | Path, label: str) -> Path:
    """Resolve `path` and require that it exists on disk."""

    resolved = Path(path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"{label} not found: {resolved}")
    return resolved


def _write_load_progress(label: str, current: int, total: int) -> None:
    """Render a simple in-terminal progress bar for HDF5 loading work."""

    if total <= 0:
        return
    clamped = min(current, total)
    width = 30
    fraction = clamped / total
    filled = int(width * fraction)
    bar = f"[{'#' * filled}{'-' * (width - filled)}]"
    percent = int(fraction * 100)
    sys.stderr.write(f"\r{label} {bar} {percent:3d}% ({clamped}/{total} rows)")
    sys.stderr.flush()
    if clamped >= total:
        sys.stderr.write("\n")
        sys.stderr.flush()


def _resolve_transport_hdf5_path(
    config: SimConfig | None,
    transport_hdf5_path: str | Path | None,
) -> Path:
    """Resolve the transport HDF5 path from an explicit path or `SimConfig`."""

    if transport_hdf5_path is not None:
        return _require_existing_path(transport_hdf5_path, "Transport HDF5 file")
    if config is None:
        raise ValueError(
            "`config` is required when `transport_hdf5_path` is not provided."
        )
    return _require_existing_path(
        resolve_transport_paths(config).output_hdf5,
        "Transport HDF5 file",
    )


def _resolve_source_hdf5_path(
    transport_path: Path,
    source_hdf5_path: str | Path | None,
) -> Path:
    """Resolve the source-photon HDF5 path from explicit input or transport metadata."""

    if source_hdf5_path is not None:
        return _require_existing_path(source_hdf5_path, "Source photon HDF5 file")

    with h5py.File(transport_path, "r") as transport_handle:
        source_hdf5_attr = transport_handle.attrs.get("source_hdf5")
        if source_hdf5_attr is None:
            raise KeyError(
                "Transport HDF5 is missing the `source_hdf5` attribute needed "
                "to resolve the source photon file."
            )
    return _require_existing_path(
        source_hdf5_attr,
        "Source photon HDF5 file",
    )


def resolve_intensifier_input_hdf5_paths(
    config: SimConfig | None,
    *,
    transport_hdf5_path: str | Path | None = None,
    source_hdf5_path: str | Path | None = None,
) -> tuple[Path, Path]:
    """Resolve transport/source HDF5 paths for intensifier input loading."""

    transport_path = _resolve_transport_hdf5_path(
        config,
        transport_hdf5_path,
    )
    source_path = _resolve_source_hdf5_path(transport_path, source_hdf5_path)
    return transport_path, source_path


def intensifier_output_hdf5_path_from_sim_config(config: SimConfig) -> Path:
    """Return the default intensifier output HDF5 path under `run_root/sensor/`."""

    run_paths = resolve_run_environment_paths(config)
    sensor_dir = (run_paths.run_root / "sensor").resolve()
    sub_run_number = config.metadata.run_environment.sub_run_number
    filename = f"{artifact_stem_for_sub_run('intensifier_output_events', sub_run_number)}.h5"
    return (sensor_dir / filename).resolve()


def _resolve_intensifier_output_hdf5_path(
    config: SimConfig,
    output_hdf5_path: str | Path | None,
) -> Path:
    """Resolve an explicit or config-derived intensifier output HDF5 path."""

    if output_hdf5_path is not None:
        return Path(output_hdf5_path).resolve()
    return intensifier_output_hdf5_path_from_sim_config(config)


def intensifier_output_batch_to_structured_array(
    output_events: IntensifierOutputBatch,
) -> np.ndarray:
    """Convert one intensifier output batch into the canonical HDF5 dtype."""

    structured = np.empty(len(output_events), dtype=_INTENSIFIER_OUTPUT_DTYPE)
    structured["source_photon_index"] = output_events.source_photon_index
    structured["gun_call_id"] = output_events.gun_call_id
    structured["primary_track_id"] = output_events.primary_track_id
    structured["secondary_track_id"] = output_events.secondary_track_id
    structured["photon_track_id"] = output_events.photon_track_id
    structured["output_x_mm"] = output_events.output_x_mm
    structured["output_y_mm"] = output_events.output_y_mm
    structured["output_time_ns"] = output_events.output_time_ns
    structured["signal_amplitude_arb"] = output_events.signal_amplitude_arb
    structured["total_gain"] = output_events.total_gain
    structured["wavelength_nm"] = output_events.wavelength_nm
    return structured


def write_intensifier_output_hdf5(
    output_events: IntensifierOutputBatch,
    *,
    config: SimConfig,
    transport_hdf5_path: str | Path | None = None,
    output_hdf5_path: str | Path | None = None,
) -> Path:
    """Write intensifier output events to a standalone HDF5 file."""

    transport_path, source_path = resolve_intensifier_input_hdf5_paths(
        config,
        transport_hdf5_path=transport_hdf5_path,
    )
    output_path = _resolve_intensifier_output_hdf5_path(config, output_hdf5_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    structured = intensifier_output_batch_to_structured_array(output_events)
    intensifier = config.intensifier
    if intensifier is None:
        raise ValueError("`config.intensifier` is required to write intensifier output.")

    with h5py.File(transport_path, "r") as transport_handle, h5py.File(
        output_path,
        "w",
    ) as output_handle:
        _copy_dataset_if_present(transport_handle, output_handle, DATASET_PRIMARIES)
        _copy_dataset_if_present(transport_handle, output_handle, DATASET_SECONDARIES)
        output_handle.create_dataset(DATASET_INTENSIFIER_OUTPUT_EVENTS, data=structured)

        output_handle.attrs["source_hdf5"] = str(source_path)
        output_handle.attrs["transport_hdf5"] = str(transport_path)
        output_handle.attrs["run_id"] = config.metadata.run_environment.simulation_run_id
        output_handle.attrs["intensifier_model"] = intensifier.model
        output_handle.attrs["generated_utc"] = datetime.now(timezone.utc).isoformat()

    return output_path


def load_transported_photon_batch(
    transport_hdf5_path: str | Path,
    *,
    source_hdf5_path: str | Path | None = None,
    require_in_bounds: bool = True,
    show_progress: bool = False,
    chunk_rows: int = _DEFAULT_LOAD_CHUNK_ROWS,
) -> TransportedPhotonBatch:
    """Load usable transported photons and source timing/wavelength into one batch."""

    transport_path = _resolve_transport_hdf5_path(None, transport_hdf5_path)
    del source_hdf5_path
    logger = get_logger()
    if chunk_rows <= 0:
        raise ValueError("`chunk_rows` must be > 0.")

    with h5py.File(transport_path, "r") as transport_handle:
        if DATASET_TRANSPORTED_PHOTONS not in transport_handle:
            raise KeyError(
                f"Dataset '{DATASET_TRANSPORTED_PHOTONS}' not found in {transport_path}"
            )

        transported_ds = transport_handle[DATASET_TRANSPORTED_PHOTONS]
        transported_fields = transported_ds.dtype.names or ()
        _require_fields(
            DATASET_TRANSPORTED_PHOTONS,
            transported_fields,
            _REQUIRED_TRANSPORT_FIELDS,
        )

        total_transport_rows = int(transported_ds.shape[0])
        source_index_parts: list[np.ndarray] = []
        gun_call_parts: list[np.ndarray] = []
        primary_track_parts: list[np.ndarray] = []
        secondary_track_parts: list[np.ndarray] = []
        photon_track_parts: list[np.ndarray] = []
        x_parts: list[np.ndarray] = []
        y_parts: list[np.ndarray] = []
        z_parts: list[np.ndarray] = []
        time_parts: list[np.ndarray] = []
        wavelength_parts: list[np.ndarray] = []
        selected_row_count = 0

        for start in range(0, total_transport_rows, chunk_rows):
            stop = min(start + chunk_rows, total_transport_rows)
            reached_mask = np.ones(stop - start, dtype=bool)
            if require_in_bounds:
                reached_mask &= np.asarray(
                    transported_ds["in_bounds"][start:stop],
                    dtype=bool,
                )

            if np.any(reached_mask):
                selected_chunk = transported_ds[start:stop][reached_mask]
                source_index_parts.append(
                    np.asarray(selected_chunk["source_photon_index"], dtype=np.int64)
                )
                gun_call_parts.append(
                    np.asarray(selected_chunk["gun_call_id"], dtype=np.int64)
                )
                primary_track_parts.append(
                    np.asarray(selected_chunk["primary_track_id"], dtype=np.int32)
                )
                secondary_track_parts.append(
                    np.asarray(selected_chunk["secondary_track_id"], dtype=np.int32)
                )
                photon_track_parts.append(
                    np.asarray(selected_chunk["photon_track_id"], dtype=np.int32)
                )
                x_parts.append(
                    np.asarray(selected_chunk["intensifier_hit_x_mm"], dtype=np.float64)
                )
                y_parts.append(
                    np.asarray(selected_chunk["intensifier_hit_y_mm"], dtype=np.float64)
                )
                z_parts.append(
                    np.asarray(selected_chunk["intensifier_hit_z_mm"], dtype=np.float64)
                )
                time_parts.append(
                    np.asarray(selected_chunk["intensifier_hit_time_ns"], dtype=np.float64)
                )
                wavelength_parts.append(
                    np.asarray(
                        selected_chunk["intensifier_hit_wavelength_nm"],
                        dtype=np.float64,
                    )
                )
                selected_row_count += int(np.count_nonzero(reached_mask))

            if show_progress:
                _write_load_progress("Intensifier load", stop, total_transport_rows)

        if selected_row_count == 0:
            return TransportedPhotonBatch.empty()

        logger.info(
            "[intensifier] Selected transported photons for intensifier input: "
            f"{selected_row_count}"
        )
        source_indices = np.concatenate(source_index_parts)
        gun_call_id = np.concatenate(gun_call_parts)
        primary_track_id = np.concatenate(primary_track_parts)
        secondary_track_id = np.concatenate(secondary_track_parts)
        photon_track_id = np.concatenate(photon_track_parts)
        x_mm = np.concatenate(x_parts)
        y_mm = np.concatenate(y_parts)
        z_mm = np.concatenate(z_parts)

        return TransportedPhotonBatch(
            source_photon_index=source_indices,
            gun_call_id=gun_call_id,
            primary_track_id=primary_track_id,
            secondary_track_id=secondary_track_id,
            photon_track_id=photon_track_id,
            x_mm=x_mm,
            y_mm=y_mm,
            z_mm=z_mm,
            time_ns=np.concatenate(time_parts),
            wavelength_nm=np.concatenate(wavelength_parts),
        )


def load_transported_photon_batch_from_sim_config(
    config,
    *,
    transport_hdf5_path: str | Path | None = None,
    source_hdf5_path: str | Path | None = None,
    require_in_bounds: bool = True,
    show_progress: bool | None = None,
) -> TransportedPhotonBatch:
    """Resolve HDF5 input paths from `SimConfig` and load one photon batch."""

    del source_hdf5_path
    transport_path = _resolve_transport_hdf5_path(config, transport_hdf5_path)
    return load_transported_photon_batch(
        transport_path,
        require_in_bounds=require_in_bounds,
        show_progress=(
            bool(config.runner.show_progress)
            if show_progress is None
            else bool(show_progress)
        ),
    )
