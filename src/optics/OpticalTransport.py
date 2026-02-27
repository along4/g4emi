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
import sys
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
    from src.config.ConfigIO import (
        DEFAULT_OUTPUT_FILENAME_BASE,
        from_yaml,
        resolve_run_environment_paths,
        validate_run_environment,
    )
    from src.config.SimConfig import SimConfig
    from src.optics.LensModels import LensModel, resolve_lens_path
except ModuleNotFoundError:
    # Support direct execution when repository root is not on sys.path.
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from src.config.ConfigIO import (
        DEFAULT_OUTPUT_FILENAME_BASE,
        from_yaml,
        resolve_run_environment_paths,
        validate_run_environment,
    )
    from src.config.SimConfig import SimConfig
    from src.optics.LensModels import LensModel, resolve_lens_path


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
    ]
)


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
    ray_engine: str
    total_photons: int
    transported_photons: int
    missed_photons: int


class RayOpticsLensTracer:
    """`rayoptics` implementation of photon tracing for one Zemax lens model."""

    engine_name = "rayoptics"

    def __init__(
        self,
        lens_zmx_path: str | Path,
        *,
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
        # rayoptics expects a pathlib.Path-like object here on newer releases.
        loaded = zmxread.read_lens_file(self.lens_zmx_path, info=False)
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
    """Run optical transport using a validated `SimConfig` object."""

    assumptions = config.optical.transport_assumptions
    defaults = resolve_transport_paths(config)
    run_paths = resolve_run_environment_paths(config)
    run_paths.log.mkdir(parents=True, exist_ok=True)
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

    lens = _primary_lens_model(config)
    tracer_impl = (
        tracer
        if tracer is not None
        else RayOpticsLensTracer(
            lens.zmx_path,
            interface_represents_lens_entrance=(
                assumptions.optical_interface_represents == "lens_entrance_plane"
            ),
            zmx_log_directory=run_paths.log,
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows, transported_count = _transport_rows(input_path, tracer_impl)

    with h5py.File(input_path, "r") as src, h5py.File(output_path, "w") as dst:
        _copy_dataset_if_present(src, dst, "primaries")
        _copy_dataset_if_present(src, dst, "secondaries")
        dst.create_dataset("transported_photons", data=rows)

        dst.attrs["source_hdf5"] = str(input_path)
        dst.attrs["run_id"] = config.metadata.run_environment.simulation_run_id
        dst.attrs["lens_name"] = lens.name
        dst.attrs["lens_zmx_path"] = str(lens.zmx_path)
        dst.attrs["object_plane"] = assumptions.object_plane
        dst.attrs["optical_interface_represents"] = (
            assumptions.optical_interface_represents
        )
        dst.attrs["transport_engine"] = getattr(
            tracer_impl, "engine_name", tracer_impl.__class__.__name__
        )
        dst.attrs["generated_utc"] = datetime.now(timezone.utc).isoformat()

    total = int(len(rows))
    return TransportSummary(
        input_hdf5=input_path,
        output_hdf5=output_path,
        lens_name=lens.name,
        lens_zmx_path=lens.zmx_path,
        ray_engine=getattr(tracer_impl, "engine_name", tracer_impl.__class__.__name__),
        total_photons=total,
        transported_photons=transported_count,
        missed_photons=total - transported_count,
    )


def _primary_lens_model(config: SimConfig) -> LensModel:
    """Resolve and parse the primary lens from `config.optical.lenses`."""

    primary_lens = next(lens for lens in config.optical.lenses if lens.primary)
    lens_path = resolve_lens_path(primary_lens.zmx_file)
    return LensModel.from_zmx(lens_path, name=primary_lens.name)


def _transport_rows(
    input_hdf5_path: Path,
    tracer: PhotonTransportTracer,
) -> tuple[np.ndarray, int]:
    """Build `/transported_photons` structured rows from input `/photons`."""

    with h5py.File(input_hdf5_path, "r") as handle:
        if "photons" not in handle:
            raise KeyError(f"Dataset 'photons' not found in {input_hdf5_path}")
        photons = handle["photons"][:]

    _require_photon_fields(photons.dtype.names or (), _REQUIRED_PHOTON_FIELDS)

    out = np.zeros(len(photons), dtype=_TRANSPORT_DTYPE)
    out["source_photon_index"] = np.arange(len(photons), dtype=np.int64)
    out["gun_call_id"] = np.asarray(photons["gun_call_id"], dtype=np.int64)
    out["primary_track_id"] = np.asarray(photons["primary_track_id"], dtype=np.int32)
    out["secondary_track_id"] = np.asarray(photons["secondary_track_id"], dtype=np.int32)
    out["photon_track_id"] = np.asarray(photons["photon_track_id"], dtype=np.int32)
    out["intensifier_hit_x_mm"] = np.nan
    out["intensifier_hit_y_mm"] = np.nan
    out["intensifier_hit_z_mm"] = np.nan
    out["reached_intensifier"] = False

    transported_count = 0
    for index, photon in enumerate(photons):
        x_mm = float(photon["optical_interface_hit_x_mm"])
        y_mm = float(photon["optical_interface_hit_y_mm"])
        dir_x = float(photon["optical_interface_hit_dir_x"])
        dir_y = float(photon["optical_interface_hit_dir_y"])
        dir_z = float(photon["optical_interface_hit_dir_z"])
        wvl_nm = (
            float(photon["optical_interface_hit_wavelength_nm"])
            if "optical_interface_hit_wavelength_nm" in (photons.dtype.names or ())
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
        transported_count += 1

    return out, transported_count


def _copy_dataset_if_present(
    source: h5py.File,
    destination: h5py.File,
    dataset_name: str,
) -> None:
    """Copy one dataset when present in source HDF5."""

    if dataset_name not in source:
        return
    destination.create_dataset(dataset_name, data=source[dataset_name][:])


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
