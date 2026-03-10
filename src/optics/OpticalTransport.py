"""SimConfig-driven optical transport from interface hits to lens image plane.

This module reads simulation HDF5 output (`/photons` interface hits) and
propagates each photon through a Zemax lens prescription via `rayoptics`.
Results are written to a secondary HDF5 file under the transport stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Protocol

try:
    import h5py
except ModuleNotFoundError as exc:  # pragma: no cover - dependency availability varies
    raise ModuleNotFoundError(
        "h5py is required for optical transport. "
        "Install project dependencies (for example: pixi install)."
    ) from exc
import numpy as np

try:
    from src.common.logger import ensure_run_logger, get_logger
    from src.config.ConfigIO import (
        DEFAULT_OUTPUT_FILENAME_BASE,
        from_yaml,
        resolve_run_environment_paths,
        validate_run_environment,
    )
    from src.config.SimConfig import SimConfig
    from src.optics.LensModels import LensModel, resolve_lens_path, resolve_smx_path
except ModuleNotFoundError:
    # Support direct execution when repository root is not on sys.path.
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from src.common.logger import ensure_run_logger, get_logger
    from src.config.ConfigIO import (
        DEFAULT_OUTPUT_FILENAME_BASE,
        from_yaml,
        resolve_run_environment_paths,
        validate_run_environment,
    )
    from src.config.SimConfig import SimConfig
    from src.optics.LensModels import LensModel, resolve_lens_path, resolve_smx_path


DEFAULT_TRANSPORT_OUTPUT_FILENAME = "photons_intensifier_hits.h5"
DEFAULT_INPUT_HDF5_FILENAME = f"{DEFAULT_OUTPUT_FILENAME_BASE}.h5"

_REQUIRED_PHOTON_FIELDS = (
    "gun_call_id",
    "primary_track_id",
    "secondary_track_id",
    "photon_track_id",
    "optical_interface_hit_x_mm",
    "optical_interface_hit_y_mm",
    "optical_interface_hit_dir_x",
    "optical_interface_hit_dir_y",
    "optical_interface_hit_dir_z",
)

_TRANSPORT_DTYPE = np.dtype(
    [
        ("source_photon_index", np.int64),
        ("gun_call_id", np.int64),
        ("primary_track_id", np.int32),
        ("secondary_track_id", np.int32),
        ("photon_track_id", np.int32),
        ("intensifier_hit_x_mm", np.float64),
        ("intensifier_hit_y_mm", np.float64),
        ("intensifier_hit_z_mm", np.float64),
        ("reached_intensifier", np.bool_),
        ("in_bounds", np.bool_),
    ]
)


# Binary mebibyte unit used for `TransportChunkTargetMiB` calculations.
_MIB = 1024 * 1024


class PhotonTransportTracer(Protocol):
    """Photon tracer contract used by `transport_from_sim_config`."""

    engine_name: str

    def trace_to_sensor(
        self,
        *,
        x_mm: float,
        y_mm: float,
        dir_x: float,
        dir_y: float,
        dir_z: float,
        wavelength_nm: float | None,
    ) -> tuple[float, float, float] | None:
        """Return sensor hit `(x_mm, y_mm, z_mm)` or `None` when missed."""


@dataclass(frozen=True)
class TransportPaths:
    """Resolved input/output HDF5 path pair for a transport run."""

    input_hdf5: Path
    output_hdf5: Path


@dataclass(frozen=True)
class TransportSummary:
    """Summary of one optical transport run."""

    input_hdf5: Path
    output_hdf5: Path
    lens_name: str
    lens_zmx_path: Path
    lens_smx_path: Path | None
    ray_engine: str
    total_photons: int
    transported_photons: int
    missed_photons: int


@dataclass(frozen=True)
class IntensifierInputScreen:
    """Active-area geometry in intensifier input-plane coordinates."""

    image_circle_diameter_mm: float
    center_x_mm: float
    center_y_mm: float
    magnification: float
    coordinate_frame: str


class RayOpticsLensTracer:
    """`rayoptics` implementation of photon tracing for one Zemax lens model."""

    engine_name = "rayoptics"

    def __init__(
        self,
        lens_zmx_path: str | Path,
        *,
        lens_smx_path: str | Path | None = None,
        interface_represents_lens_entrance: bool = True,
        zmx_log_directory: str | Path | None = None,
    ) -> None:
        try:
            from rayoptics.raytr import trace
            from rayoptics.zemax import zmxread
        except ModuleNotFoundError as exc:  # pragma: no cover - runtime dependency
            raise ModuleNotFoundError(
                "rayoptics is required for ray-tracing transport. "
                "Install project dependencies (for example: pixi install)."
            ) from exc

        self._configure_zmxread_logger(zmx_log_directory)
        self._trace = trace
        self.lens_zmx_path = Path(lens_zmx_path).resolve()
        self.lens_smx_path = (
            Path(lens_smx_path).resolve() if lens_smx_path is not None else None
        )
        self._temp_lens_dir: tempfile.TemporaryDirectory[str] | None = None
        zmx_for_read = self._prepare_lens_pair_for_rayoptics(
            self.lens_zmx_path,
            self.lens_smx_path,
        )
        # rayoptics expects a pathlib.Path-like object here on newer releases.
        loaded = zmxread.read_lens_file(zmx_for_read, info=False)
        # API compatibility:
        # - some versions return OpticalModel
        # - others return (OpticalModel, info)
        self._opt_model = loaded[0] if isinstance(loaded, tuple) else loaded
        self._seq_model = self._extract_seq_model(self._opt_model)
        self._supported_wavelengths_nm = self._extract_supported_wavelengths()
        if interface_represents_lens_entrance:
            self._rebase_object_gap_to_interface()
        self._default_wavelength_nm = self._central_wavelength_nm()

    @staticmethod
    def _configure_zmxread_logger(zmx_log_directory: str | Path | None) -> None:
        """Route rayoptics Zemax parser log into requested run logs directory."""

        if zmx_log_directory is None:
            return

        log_dir = Path(zmx_log_directory).resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "zmx_read_lens.log"
        target_logger = logging.getLogger("rayoptics.zemax.zmxread")

        # Remove preconfigured file handlers from rayoptics so one log file is
        # written into this run's logs directory instead of cwd.
        for handler in list(target_logger.handlers):
            if isinstance(handler, logging.FileHandler):
                target_logger.removeHandler(handler)
                try:
                    handler.close()
                except Exception:
                    pass
                continue

        file_handler = logging.FileHandler(log_path, mode="w", delay=True)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        target_logger.addHandler(file_handler)
        target_logger.setLevel(logging.INFO)
        target_logger.propagate = False

    def _prepare_lens_pair_for_rayoptics(
        self,
        zmx_path: Path,
        smx_path: Path | None,
    ) -> Path:
        """Stage `.zmx`/`.smx` into one directory for rayoptics sidecar loading."""

        if smx_path is None:
            return zmx_path

        sibling_smx = zmx_path.with_suffix(".smx")
        if sibling_smx.exists() and sibling_smx.resolve() == smx_path.resolve():
            return zmx_path

        temp_dir = tempfile.TemporaryDirectory(prefix="rayoptics_lens_")
        self._temp_lens_dir = temp_dir
        temp_path = Path(temp_dir.name)
        staged_zmx = temp_path / zmx_path.name
        staged_smx = staged_zmx.with_suffix(".smx")
        shutil.copy2(zmx_path, staged_zmx)
        shutil.copy2(smx_path, staged_smx)
        return staged_zmx

    @staticmethod
    def _extract_seq_model(opt_model: object) -> object:
        """Return sequential model from OpticalModel across API variants."""

        if hasattr(opt_model, "seq_model"):
            return getattr(opt_model, "seq_model")
        try:
            return opt_model["seq_model"]  # type: ignore[index]
        except Exception as exc:
            raise RuntimeError(
                "Could not access `seq_model` from rayoptics OpticalModel."
            ) from exc

    def _central_wavelength_nm(self) -> float:
        """Best-effort central wavelength lookup from imported sequential model."""

        seq_model = self._seq_model
        try:
            central = float(seq_model.central_wavelength())
            if np.isfinite(central) and central > 0.0:
                return central
        except Exception:
            pass
        try:
            if len(seq_model.wvlns) > 0:  # type: ignore[attr-defined]
                return float(seq_model.wvlns[0])  # type: ignore[attr-defined]
        except Exception:
            pass
        return 550.0

    def _extract_supported_wavelengths(self) -> tuple[float, ...]:
        """Return supported sequential-model wavelength samples in nm."""

        seq_model = self._seq_model
        try:
            wvlns = tuple(float(value) for value in seq_model.wvlns)  # type: ignore[attr-defined]
        except Exception:
            return ()
        return tuple(value for value in wvlns if np.isfinite(value) and value > 0.0)

    def _rebase_object_gap_to_interface(self) -> None:
        """Set object gap to 0 mm so traced starts are at lens-entrance plane."""

        seq_model = self._seq_model
        try:
            if len(seq_model.gaps) > 0:  # type: ignore[attr-defined]
                seq_model.gaps[0].thi = 0.0  # type: ignore[attr-defined]
        except Exception:
            return
        try:
            seq_model.update_model()  # type: ignore[attr-defined]
            return
        except Exception:
            pass
        try:
            self._opt_model.update_model()  # type: ignore[attr-defined]
        except Exception:
            pass

    def trace_to_sensor(
        self,
        *,
        x_mm: float,
        y_mm: float,
        dir_x: float,
        dir_y: float,
        dir_z: float,
        wavelength_nm: float | None,
    ) -> tuple[float, float, float] | None:
        """Trace one ray from interface coordinates to the model image plane."""

        direction = _normalized_direction(dir_x, dir_y, dir_z)
        if direction is None:
            return None

        # Align direction with the sequential-model object-side z-propagation.
        z_dir = getattr(self._seq_model, "z_dir", None)
        if z_dir is not None and len(z_dir) > 0:
            try:
                if float(direction[2]) * float(z_dir[0]) < 0.0:
                    direction = -direction
            except Exception:
                pass

        start_point = np.array([x_mm, y_mm, 0.0], dtype=float)
        wvl_nm = _clean_wavelength_nm(
            wavelength_nm,
            default_nm=self._default_wavelength_nm,
            supported_wavelengths_nm=self._supported_wavelengths_nm,
        )

        try:
            ray_pkg = self._trace.trace(
                self._seq_model,
                start_point,
                direction,
                wvl_nm,
                check_apertures=True,
                apply_vignetting=False,
            )
        except Exception:
            return None

        try:
            # `ray_pkg[0]` is the list of ray segments; each segment stores
            # intersection point as the first tuple/list item.
            image_point = np.asarray(ray_pkg[0][-1][0], dtype=float)
        except Exception:
            return None

        if image_point.size < 3 or not np.all(np.isfinite(image_point[:3])):
            return None

        return (
            float(image_point[0]),
            float(image_point[1]),
            float(image_point[2]),
        )


def resolve_transport_paths(
    config: SimConfig,
    *,
    input_filename: str = DEFAULT_INPUT_HDF5_FILENAME,
    output_filename: str = DEFAULT_TRANSPORT_OUTPUT_FILENAME,
) -> TransportPaths:
    """Resolve default transport input/output HDF5 paths from `SimConfig`."""

    validate_run_environment(
        config,
        targets=("data", "run_root", "simulated_photons", "transported_photons"),
        create_directories=True,
    )
    run_paths = resolve_run_environment_paths(config)
    return TransportPaths(
        input_hdf5=(run_paths.simulated_photons / input_filename).resolve(),
        output_hdf5=(run_paths.transported_photons / output_filename).resolve(),
    )


def transport_from_yaml(
    yaml_path: str | Path,
    *,
    input_hdf5_path: str | Path | None = None,
    output_hdf5_path: str | Path | None = None,
    overwrite: bool = True,
) -> TransportSummary:
    """Load `SimConfig` from YAML and run optical transport."""

    config = from_yaml(yaml_path)
    return transport_from_sim_config(
        config,
        input_hdf5_path=input_hdf5_path,
        output_hdf5_path=output_hdf5_path,
        overwrite=overwrite,
    )


def transport_from_sim_config(
    config: SimConfig,
    *,
    input_hdf5_path: str | Path | None = None,
    output_hdf5_path: str | Path | None = None,
    overwrite: bool = True,
    tracer: PhotonTransportTracer | None = None,
) -> TransportSummary:
    """Run optical transport using a validated `SimConfig` object.

    Implementation notes:
    - Output is written to a single HDF5 file.
    - `/transported_photons` is created as a chunked dataset sized to the
      input `/photons` row count so source-index linkage remains one-to-one.
    - Processing happens in chunk-sized batches to bound memory usage by
      roughly one input chunk + one output chunk at a time.
    """

    assumptions = config.optical.transport_assumptions
    input_screen = _resolve_intensifier_input_screen(config)
    defaults = resolve_transport_paths(config)
    run_paths = resolve_run_environment_paths(config)
    log_path = ensure_run_logger(config)
    logger = get_logger()
    input_path = (
        Path(input_hdf5_path).resolve()
        if input_hdf5_path is not None
        else defaults.input_hdf5
    )
    output_path = (
        Path(output_hdf5_path).resolve()
        if output_hdf5_path is not None
        else defaults.output_hdf5
    )

    if input_path == output_path:
        raise ValueError("Input and output HDF5 paths must be distinct.")
    if not input_path.exists():
        raise FileNotFoundError(f"Input HDF5 file not found: {input_path}")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {output_path}")

    lens, smx_path = _primary_lens_model(config)
    logger.info(f"Run log: {log_path}")
    logger.info(f"Starting optical transport for run '{config.metadata.run_environment.simulation_run_id}'.")
    logger.info(f"Transport input HDF5: {input_path}")
    logger.info(f"Transport output HDF5: {output_path}")
    logger.debug(f"Transport log directory: {run_paths.log}")
    logger.debug(f"Transport overwrite enabled: {overwrite}")
    logger.info(f"Primary lens: {lens.name} ({lens.zmx_path})")
    tracer_impl = (
        tracer
        if tracer is not None
        else RayOpticsLensTracer(
            lens.zmx_path,
            lens_smx_path=smx_path,
            interface_represents_lens_entrance=(
                assumptions.optical_interface_represents == "lens_entrance_plane"
            ),
            zmx_log_directory=run_paths.log,
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with h5py.File(input_path, "r") as src, h5py.File(output_path, "w") as dst:
        _copy_dataset_if_present(src, dst, "primaries")
        _copy_dataset_if_present(src, dst, "secondaries")

        if "photons" not in src:
            raise KeyError(f"Dataset 'photons' not found in {input_path}")
        photons_ds = src["photons"]
        photon_field_names = photons_ds.dtype.names or ()
        _require_photon_fields(photon_field_names, _REQUIRED_PHOTON_FIELDS)

        total = len(photons_ds)
        logger.info(f"Loaded {total} photons for transport.")
        # Resolve effective row chunking from config.
        # - explicit integer uses caller-provided chunk rows
        # - "auto" derives rows from target MiB and row byte sizes
        chunk_rows = _resolve_transport_chunk_rows(
            config,
            total_rows=total,
            input_row_nbytes=photons_ds.dtype.itemsize,
            output_row_nbytes=_TRANSPORT_DTYPE.itemsize,
        )
        logger.debug(f"Transport chunk rows: {chunk_rows}")
        # Create one fixed-size output dataset (not resizable) so row i always
        # corresponds to source photon i. Missed photons keep NaN hit values.
        transported_ds = _create_transported_dataset(
            dst,
            total_rows=total,
            chunk_rows=chunk_rows,
        )

        transported_count = 0
        if total > 0:
            for start in range(0, total, chunk_rows):
                stop = min(start + chunk_rows, total)
                # Read only one photon slice into memory.
                photons_chunk = photons_ds[start:stop]
                out_chunk, hit_count = _transport_rows_chunk(
                    photons_chunk,
                    tracer_impl,
                    source_index_offset=start,
                    photon_field_names=photon_field_names,
                    input_screen=input_screen,
                )
                # Persist this slice immediately to keep peak memory bounded.
                transported_ds[start:stop] = out_chunk
                transported_count += hit_count

        dst.attrs["source_hdf5"] = str(input_path)
        dst.attrs["run_id"] = config.metadata.run_environment.simulation_run_id
        dst.attrs["lens_name"] = lens.name
        dst.attrs["lens_zmx_path"] = str(lens.zmx_path)
        if smx_path is not None:
            dst.attrs["lens_smx_path"] = str(smx_path)
        dst.attrs["object_plane"] = assumptions.object_plane
        dst.attrs["optical_interface_represents"] = (
            assumptions.optical_interface_represents
        )
        dst.attrs["transport_engine"] = getattr(
            tracer_impl, "engine_name", tracer_impl.__class__.__name__
        )
        dst.attrs["transport_chunk_rows"] = int(chunk_rows)
        dst.attrs["transport_chunk_target_mib"] = float(
            config.metadata.run_environment.output_info.transport_chunk_target_mib
        )
        if input_screen is not None:
            dst.attrs["intensifier_model"] = config.intensifier.model
            dst.attrs["intensifier_input_screen_defined"] = True
            dst.attrs["intensifier_input_screen_diameter_mm"] = float(
                input_screen.image_circle_diameter_mm
            )
            dst.attrs["intensifier_input_screen_center_mm"] = np.array(
                [input_screen.center_x_mm, input_screen.center_y_mm],
                dtype=np.float64,
            )
            dst.attrs["intensifier_input_screen_magnification"] = float(
                input_screen.magnification
            )
            dst.attrs["intensifier_input_screen_coordinate_frame"] = (
                input_screen.coordinate_frame
            )
        else:
            dst.attrs["intensifier_input_screen_defined"] = False
        dst.attrs["generated_utc"] = datetime.now(timezone.utc).isoformat()

    summary = TransportSummary(
        input_hdf5=input_path,
        output_hdf5=output_path,
        lens_name=lens.name,
        lens_zmx_path=lens.zmx_path,
        lens_smx_path=smx_path,
        ray_engine=getattr(tracer_impl, "engine_name", tracer_impl.__class__.__name__),
        total_photons=total,
        transported_photons=transported_count,
        missed_photons=total - transported_count,
    )
    logger.info(
        "Transport finished: "
        f"total={summary.total_photons}, "
        f"transported={summary.transported_photons}, "
        f"missed={summary.missed_photons}."
    )
    logger.info(f"Transport engine: {summary.ray_engine}")
    logger.info(f"Transport output: {summary.output_hdf5}")
    return summary


def _primary_lens_model(config: SimConfig) -> tuple[LensModel, Path | None]:
    """Resolve and parse primary lens model + optional `.smx` sidecar path."""

    primary_lens = next(lens for lens in config.optical.lenses if lens.primary)
    if primary_lens.zmx_file is None:
        raise ValueError(
            "Primary lens is missing a resolved `zmxFile` path. "
            "When specifying a lens via `catalogId`, the `SimConfig` must be "
            "hydrated (for example by loading it with `ConfigIO.from_yaml(...)` "
            "or by calling `transport_from_yaml(...)`) so that `catalogId` is "
            "resolved to `zmxFile` before calling `transport_from_sim_config`."
        )
    lens_path = resolve_lens_path(primary_lens.zmx_file)
    smx_path = resolve_smx_path(primary_lens.smx_file, zmx_path=lens_path)
    return LensModel.from_zmx(lens_path, name=primary_lens.name), smx_path


def _resolve_intensifier_input_screen(config: SimConfig) -> IntensifierInputScreen | None:
    """Extract optional intensifier active-area definition from `SimConfig`."""

    intensifier = config.intensifier
    if intensifier is None:
        return None

    input_screen = intensifier.input_screen
    return IntensifierInputScreen(
        image_circle_diameter_mm=float(input_screen.image_circle_diameter_mm),
        center_x_mm=float(input_screen.center_mm[0]),
        center_y_mm=float(input_screen.center_mm[1]),
        magnification=float(input_screen.magnification),
        coordinate_frame=input_screen.coordinate_frame,
    )


def _is_in_intensifier_input_screen(
    x_mm: float,
    y_mm: float,
    *,
    input_screen: IntensifierInputScreen,
) -> bool:
    """Return whether a hit lies within the configured circular image circle."""

    radius_mm = 0.5 * float(input_screen.image_circle_diameter_mm)
    dx_mm = float(x_mm) - float(input_screen.center_x_mm)
    dy_mm = float(y_mm) - float(input_screen.center_y_mm)
    return (dx_mm * dx_mm) + (dy_mm * dy_mm) <= (radius_mm * radius_mm)


def _transport_rows_chunk(
    photons_chunk: np.ndarray,
    tracer: PhotonTransportTracer,
    *,
    source_index_offset: int,
    photon_field_names: tuple[str, ...] | list[str],
    input_screen: IntensifierInputScreen | None,
) -> tuple[np.ndarray, int]:
    """Build one output chunk for `/transported_photons`.

    The returned array length equals `len(photons_chunk)` and is initialized
    with NaN intensifier coordinates + `reached_intensifier=False` so misses
    require no special post-processing.
    """

    out = np.zeros(len(photons_chunk), dtype=_TRANSPORT_DTYPE)
    out["source_photon_index"] = np.arange(
        source_index_offset,
        source_index_offset + len(photons_chunk),
        dtype=np.int64,
    )
    out["gun_call_id"] = np.asarray(photons_chunk["gun_call_id"], dtype=np.int64)
    out["primary_track_id"] = np.asarray(photons_chunk["primary_track_id"], dtype=np.int32)
    out["secondary_track_id"] = np.asarray(
        photons_chunk["secondary_track_id"],
        dtype=np.int32,
    )
    out["photon_track_id"] = np.asarray(photons_chunk["photon_track_id"], dtype=np.int32)
    out["intensifier_hit_x_mm"] = np.nan
    out["intensifier_hit_y_mm"] = np.nan
    out["intensifier_hit_z_mm"] = np.nan
    out["reached_intensifier"] = False
    out["in_bounds"] = False

    transported_count = 0
    for index, photon in enumerate(photons_chunk):
        x_mm = float(photon["optical_interface_hit_x_mm"])
        y_mm = float(photon["optical_interface_hit_y_mm"])
        dir_x = float(photon["optical_interface_hit_dir_x"])
        dir_y = float(photon["optical_interface_hit_dir_y"])
        dir_z = float(photon["optical_interface_hit_dir_z"])
        wvl_nm = (
            float(photon["optical_interface_hit_wavelength_nm"])
            if "optical_interface_hit_wavelength_nm" in photon_field_names
            else None
        )

        if not np.isfinite(x_mm) or not np.isfinite(y_mm):
            continue

        hit = tracer.trace_to_sensor(
            x_mm=x_mm,
            y_mm=y_mm,
            dir_x=dir_x,
            dir_y=dir_y,
            dir_z=dir_z,
            wavelength_nm=wvl_nm,
        )
        if hit is None:
            continue

        sensor_x, sensor_y, sensor_z = hit
        if not all(np.isfinite(v) for v in (sensor_x, sensor_y, sensor_z)):
            continue

        out["intensifier_hit_x_mm"][index] = float(sensor_x)
        out["intensifier_hit_y_mm"][index] = float(sensor_y)
        out["intensifier_hit_z_mm"][index] = float(sensor_z)
        out["reached_intensifier"][index] = True
        if input_screen is None:
            out["in_bounds"][index] = True
        else:
            out["in_bounds"][index] = _is_in_intensifier_input_screen(
                sensor_x,
                sensor_y,
                input_screen=input_screen,
            )
        transported_count += 1

    return out, transported_count


def _resolve_transport_chunk_rows(
    config: SimConfig,
    *,
    total_rows: int,
    input_row_nbytes: int,
    output_row_nbytes: int,
) -> int:
    """Resolve effective transport chunk rows from config and row sizes.

    Auto mode uses:
    `rows = floor(target_mib * 1024^2 / (input_row_nbytes + output_row_nbytes))`

    The final value is clamped to `[1, total_rows]` so chunking is always
    valid even for tiny inputs or very large target budgets.
    """

    if total_rows <= 0:
        return 1

    output_info = config.metadata.run_environment.output_info
    configured = output_info.transport_chunk_rows
    if isinstance(configured, int):
        requested = configured
    else:
        row_nbytes = max(1, int(input_row_nbytes) + int(output_row_nbytes))
        target_nbytes = int(output_info.transport_chunk_target_mib * _MIB)
        requested = max(1, target_nbytes // row_nbytes)

    return max(1, min(total_rows, int(requested)))


def _create_transported_dataset(
    destination: h5py.File,
    *,
    total_rows: int,
    chunk_rows: int,
) -> h5py.Dataset:
    """Create `/transported_photons` dataset with stable row semantics.

    Behavior:
    - `total_rows == 0`: create empty dataset without explicit chunking.
    - `total_rows > 0`: create fixed-size chunked dataset using `chunk_rows`.

    This keeps the external file schema unchanged (one dataset in one file)
    while enabling low-memory incremental writes.
    """

    if total_rows <= 0:
        return destination.create_dataset(
            "transported_photons",
            shape=(0,),
            dtype=_TRANSPORT_DTYPE,
        )
    return destination.create_dataset(
        "transported_photons",
        shape=(total_rows,),
        dtype=_TRANSPORT_DTYPE,
        chunks=(chunk_rows,),
    )


def _copy_dataset_if_present(
    source: h5py.File,
    destination: h5py.File,
    dataset_name: str,
) -> None:
    """Copy one dataset when present in source HDF5."""

    if dataset_name not in source:
        return
    # Use HDF5's native copy to avoid loading the entire dataset into memory
    # and to preserve dataset creation properties (e.g. chunking/compression).
    source.copy(dataset_name, destination)


def _require_photon_fields(
    present_fields: tuple[str, ...] | list[str],
    required_fields: tuple[str, ...],
) -> None:
    """Raise when the input photon dataset is missing required columns."""

    present = set(present_fields)
    missing = [name for name in required_fields if name not in present]
    if missing:
        raise KeyError(
            "Input /photons dataset is missing required fields: "
            f"{missing}"
        )


def _clean_wavelength_nm(
    value: float | None,
    *,
    default_nm: float,
    supported_wavelengths_nm: tuple[float, ...] = (),
) -> float:
    """Return valid trace wavelength in nm (default or nearest supported sample)."""

    if value is None:
        return default_nm
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default_nm
    if not np.isfinite(numeric) or numeric <= 0.0:
        numeric = default_nm
    if not supported_wavelengths_nm:
        return numeric
    nearest = min(supported_wavelengths_nm, key=lambda sample: abs(sample - numeric))
    return float(nearest)


def _normalized_direction(
    dir_x: float,
    dir_y: float,
    dir_z: float,
) -> np.ndarray | None:
    """Return normalized ray direction vector or `None` for invalid input."""

    vec = np.array([dir_x, dir_y, dir_z], dtype=float)
    if not np.all(np.isfinite(vec)):
        return None
    norm = float(np.linalg.norm(vec))
    if norm <= 0.0:
        return None
    return vec / norm


__all__ = [
    "DEFAULT_INPUT_HDF5_FILENAME",
    "DEFAULT_TRANSPORT_OUTPUT_FILENAME",
    "PhotonTransportTracer",
    "RayOpticsLensTracer",
    "TransportPaths",
    "TransportSummary",
    "resolve_transport_paths",
    "transport_from_sim_config",
    "transport_from_yaml",
]
