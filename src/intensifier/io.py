"""HDF5 I/O helpers for the intensifier stage."""

from __future__ import annotations

from pathlib import Path

try:
    import h5py
except ModuleNotFoundError as exc:  # pragma: no cover - dependency availability varies
    raise ModuleNotFoundError(
        "h5py is required for intensifier HDF5 I/O. "
        "Install project dependencies (for example: pixi install)."
    ) from exc
import numpy as np

from src.common.hdf5_schema import DATASET_PHOTONS
from src.common.hdf5_schema import DATASET_TRANSPORTED_PHOTONS
from src.intensifier.models import TransportedPhotonBatch
from src.optics.OpticalTransport import resolve_transport_paths

_REQUIRED_TRANSPORT_FIELDS = (
    "source_photon_index",
    "gun_call_id",
    "primary_track_id",
    "secondary_track_id",
    "photon_track_id",
    "intensifier_hit_x_mm",
    "intensifier_hit_y_mm",
    "intensifier_hit_z_mm",
    "reached_intensifier",
    "in_bounds",
)

_REQUIRED_SOURCE_PHOTON_FIELDS = (
    "optical_interface_hit_time_ns",
    "optical_interface_hit_wavelength_nm",
)


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


def resolve_intensifier_input_hdf5_paths(
    config,
    *,
    transport_hdf5_path: str | Path | None = None,
    source_hdf5_path: str | Path | None = None,
) -> tuple[Path, Path]:
    """Resolve transport/source HDF5 paths for intensifier input loading."""

    transport_path = (
        Path(transport_hdf5_path).resolve()
        if transport_hdf5_path is not None
        else resolve_transport_paths(config).output_hdf5
    )
    if not transport_path.exists():
        raise FileNotFoundError(f"Transport HDF5 file not found: {transport_path}")

    if source_hdf5_path is not None:
        source_path = Path(source_hdf5_path).resolve()
    else:
        with h5py.File(transport_path, "r") as transport_handle:
            source_hdf5_attr = transport_handle.attrs.get("source_hdf5")
            if source_hdf5_attr is None:
                raise KeyError(
                    "Transport HDF5 is missing the `source_hdf5` attribute needed "
                    "to resolve the source photon file."
                )
            source_path = Path(str(source_hdf5_attr)).resolve()

    if not source_path.exists():
        raise FileNotFoundError(f"Source photon HDF5 file not found: {source_path}")
    return transport_path, source_path


def load_transported_photon_batch(
    transport_hdf5_path: str | Path,
    *,
    source_hdf5_path: str | Path | None = None,
    require_in_bounds: bool = True,
) -> TransportedPhotonBatch:
    """Load usable transported photons and source timing/wavelength into one batch."""

    transport_path = Path(transport_hdf5_path).resolve()
    if not transport_path.exists():
        raise FileNotFoundError(f"Transport HDF5 file not found: {transport_path}")

    if source_hdf5_path is None:
        with h5py.File(transport_path, "r") as transport_handle:
            source_hdf5_attr = transport_handle.attrs.get("source_hdf5")
            if source_hdf5_attr is None:
                raise KeyError(
                    "Transport HDF5 is missing the `source_hdf5` attribute needed "
                    "to resolve the source photon file."
                )
            source_path = Path(str(source_hdf5_attr)).resolve()
    else:
        source_path = Path(source_hdf5_path).resolve()

    if not source_path.exists():
        raise FileNotFoundError(f"Source photon HDF5 file not found: {source_path}")

    with h5py.File(transport_path, "r") as transport_handle, h5py.File(
        source_path,
        "r",
    ) as source_handle:
        if DATASET_TRANSPORTED_PHOTONS not in transport_handle:
            raise KeyError(
                f"Dataset '{DATASET_TRANSPORTED_PHOTONS}' not found in {transport_path}"
            )
        if DATASET_PHOTONS not in source_handle:
            raise KeyError(f"Dataset '{DATASET_PHOTONS}' not found in {source_path}")

        transported_ds = transport_handle[DATASET_TRANSPORTED_PHOTONS]
        source_ds = source_handle[DATASET_PHOTONS]
        transported_fields = transported_ds.dtype.names or ()
        source_fields = source_ds.dtype.names or ()
        _require_fields(
            DATASET_TRANSPORTED_PHOTONS,
            transported_fields,
            _REQUIRED_TRANSPORT_FIELDS,
        )
        _require_fields(DATASET_PHOTONS, source_fields, _REQUIRED_SOURCE_PHOTON_FIELDS)

        transported = transported_ds[:]
        mask = np.asarray(transported["reached_intensifier"], dtype=bool)
        if require_in_bounds:
            mask &= np.asarray(transported["in_bounds"], dtype=bool)

        selected = transported[mask]
        if len(selected) == 0:
            return TransportedPhotonBatch(
                source_photon_index=np.array([], dtype=np.int64),
                gun_call_id=np.array([], dtype=np.int64),
                primary_track_id=np.array([], dtype=np.int32),
                secondary_track_id=np.array([], dtype=np.int32),
                photon_track_id=np.array([], dtype=np.int32),
                x_mm=np.array([], dtype=np.float64),
                y_mm=np.array([], dtype=np.float64),
                z_mm=np.array([], dtype=np.float64),
                time_ns=np.array([], dtype=np.float64),
                wavelength_nm=np.array([], dtype=np.float64),
            )

        source_indices = np.asarray(selected["source_photon_index"], dtype=np.int64)
        source_rows = source_ds[source_indices]

        return TransportedPhotonBatch(
            source_photon_index=source_indices,
            gun_call_id=np.asarray(selected["gun_call_id"], dtype=np.int64),
            primary_track_id=np.asarray(selected["primary_track_id"], dtype=np.int32),
            secondary_track_id=np.asarray(selected["secondary_track_id"], dtype=np.int32),
            photon_track_id=np.asarray(selected["photon_track_id"], dtype=np.int32),
            x_mm=np.asarray(selected["intensifier_hit_x_mm"], dtype=np.float64),
            y_mm=np.asarray(selected["intensifier_hit_y_mm"], dtype=np.float64),
            z_mm=np.asarray(selected["intensifier_hit_z_mm"], dtype=np.float64),
            time_ns=np.asarray(source_rows["optical_interface_hit_time_ns"], dtype=np.float64),
            wavelength_nm=np.asarray(
                source_rows["optical_interface_hit_wavelength_nm"],
                dtype=np.float64,
            ),
        )


def load_transported_photon_batch_from_sim_config(
    config,
    *,
    transport_hdf5_path: str | Path | None = None,
    source_hdf5_path: str | Path | None = None,
    require_in_bounds: bool = True,
) -> TransportedPhotonBatch:
    """Resolve HDF5 input paths from `SimConfig` and load one photon batch."""

    transport_path, source_path = resolve_intensifier_input_hdf5_paths(
        config,
        transport_hdf5_path=transport_hdf5_path,
        source_hdf5_path=source_hdf5_path,
    )
    return load_transported_photon_batch(
        transport_path,
        source_hdf5_path=source_path,
        require_in_bounds=require_in_bounds,
    )
