"""Shared support for analysis unit tests."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


def _repo_root() -> Path:
    """Resolve repository root by searching parent directories."""

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "analysis").is_dir() and (parent / "pixi.toml").is_file():
            return parent
    raise RuntimeError("Could not resolve repository root from test path.")


sys.path.insert(0, str(_repo_root()))


class AnalysisTestCase(unittest.TestCase):
    """Base class that loads optional analysis-test dependencies once."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import h5py
            import matplotlib
            import numpy as np

            matplotlib.use("Agg")
            from matplotlib import pyplot as plt
        except ModuleNotFoundError as exc:
            missing = (getattr(exc, "name", "") or "").lower()
            if missing in {"h5py", "numpy", "matplotlib"}:
                raise unittest.SkipTest(
                    f"Missing dependency for analysis tests: {exc}. "
                    "Run in the project environment (for example: pixi run test-python)."
                ) from exc
            raise

        cls.h5py = h5py
        cls.np = np
        cls.plt = plt


class AnalysisDataBuilderMixin:
    """Helpers that write small HDF5 fixtures for analysis tests."""

    def _write_transport_hdf5(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        dtype = self.np.dtype(
            [
                ("intensifier_hit_x_mm", self.np.float64),
                ("intensifier_hit_y_mm", self.np.float64),
                ("reached_intensifier", self.np.bool_),
                ("in_bounds", self.np.bool_),
            ]
        )
        rows = self.np.array(
            [
                (0.0, 0.0, True, True),
                (10.0, 0.0, True, False),
                (self.np.nan, self.np.nan, False, False),
            ],
            dtype=dtype,
        )
        with self.h5py.File(path, "w") as handle:
            handle.create_dataset("transported_photons", data=rows)
            handle.attrs["intensifier_input_screen_defined"] = True
            handle.attrs["intensifier_input_screen_diameter_mm"] = 18.0
            handle.attrs["intensifier_input_screen_center_mm"] = self.np.array(
                [0.0, 0.0],
                dtype=self.np.float64,
            )
            handle.attrs["intensifier_input_screen_coordinate_frame"] = (
                "intensifier_input_plane"
            )

    def _write_photons_hdf5(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        dtype = self.np.dtype(
            [
                ("photon_origin_x_mm", self.np.float64),
                ("photon_origin_y_mm", self.np.float64),
                ("photon_scint_exit_x_mm", self.np.float64),
                ("photon_scint_exit_y_mm", self.np.float64),
            ]
        )
        rows = self.np.array(
            [
                (0.5, -0.5, 1.0, 1.0),
                (-1.0, 0.75, self.np.nan, self.np.nan),
            ],
            dtype=dtype,
        )
        with self.h5py.File(path, "w") as handle:
            handle.create_dataset("photons", data=rows)

    def _write_timing_hdf5(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        primaries_dtype = self.np.dtype(
            [
                ("gun_call_id", self.np.int64),
                ("primary_track_id", self.np.int32),
                ("primary_interaction_time_ns", self.np.float64),
            ]
        )
        photons_dtype = self.np.dtype(
            [
                ("gun_call_id", self.np.int64),
                ("primary_track_id", self.np.int32),
                ("photon_creation_time_ns", self.np.float64),
            ]
        )
        primary_rows = self.np.array(
            [
                (0, 11, 3.0),
                (0, 12, self.np.nan),
            ],
            dtype=primaries_dtype,
        )
        photon_rows = self.np.array(
            [
                (0, 11, 5.0),
                (0, 11, 8.0),
                (0, 12, 9.0),
                (0, 99, 4.0),
            ],
            dtype=photons_dtype,
        )
        with self.h5py.File(path, "w") as handle:
            handle.create_dataset("primaries", data=primary_rows)
            handle.create_dataset("photons", data=photon_rows)

    def _write_secondaries_hdf5(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        secondaries_dtype = self.np.dtype(
            [
                ("secondary_species", "S16"),
                ("secondary_origin_x_mm", self.np.float64),
                ("secondary_origin_y_mm", self.np.float64),
                ("secondary_origin_z_mm", self.np.float64),
                ("secondary_end_x_mm", self.np.float64),
                ("secondary_end_y_mm", self.np.float64),
                ("secondary_end_z_mm", self.np.float64),
            ]
        )
        secondary_rows = self.np.array(
            [
                (b"proton", 0.0, 0.0, 0.0, 3.0, 4.0, 0.0),
                (b"proton", 1.0, 2.0, 3.0, 1.0, 2.0, 9.0),
                (b"alpha", 0.0, 0.0, 0.0, 0.0, 6.0, 8.0),
                (b"alpha", 0.0, 0.0, 0.0, self.np.nan, 1.0, 1.0),
            ],
            dtype=secondaries_dtype,
        )
        with self.h5py.File(path, "w") as handle:
            handle.create_dataset("secondaries", data=secondary_rows)

    def _write_delay_sample_hdf5(self, path: Path, delays_ns) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        primaries_dtype = self.np.dtype(
            [
                ("gun_call_id", self.np.int64),
                ("primary_track_id", self.np.int32),
                ("primary_interaction_time_ns", self.np.float64),
            ]
        )
        photons_dtype = self.np.dtype(
            [
                ("gun_call_id", self.np.int64),
                ("primary_track_id", self.np.int32),
                ("photon_creation_time_ns", self.np.float64),
            ]
        )
        primary_rows = self.np.array([(0, 1, 0.0)], dtype=primaries_dtype)
        photon_rows = self.np.array(
            [(0, 1, float(delay_ns)) for delay_ns in delays_ns],
            dtype=photons_dtype,
        )
        with self.h5py.File(path, "w") as handle:
            handle.create_dataset("primaries", data=primary_rows)
            handle.create_dataset("photons", data=photon_rows)

    def _write_event_recoil_hdf5(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        primaries_dtype = self.np.dtype(
            [
                ("gun_call_id", self.np.int64),
                ("primary_species", "S16"),
                ("primary_x_mm", self.np.float64),
                ("primary_y_mm", self.np.float64),
            ]
        )
        secondaries_dtype = self.np.dtype(
            [
                ("gun_call_id", self.np.int64),
                ("secondary_track_id", self.np.int32),
                ("secondary_species", "S16"),
                ("secondary_origin_x_mm", self.np.float64),
                ("secondary_origin_y_mm", self.np.float64),
                ("secondary_origin_z_mm", self.np.float64),
                ("secondary_origin_energy_MeV", self.np.float64),
                ("secondary_end_x_mm", self.np.float64),
                ("secondary_end_y_mm", self.np.float64),
                ("secondary_end_z_mm", self.np.float64),
            ]
        )
        photons_dtype = self.np.dtype(
            [
                ("gun_call_id", self.np.int64),
                ("secondary_track_id", self.np.int32),
                ("photon_origin_x_mm", self.np.float64),
                ("photon_origin_y_mm", self.np.float64),
                ("photon_origin_z_mm", self.np.float64),
                ("photon_scint_exit_x_mm", self.np.float64),
                ("photon_scint_exit_y_mm", self.np.float64),
                ("photon_scint_exit_z_mm", self.np.float64),
            ]
        )
        primary_rows = self.np.array(
            [
                (7, b"neutron", -0.5, 0.25),
                (9, b"neutron", 1.8, 1.7),
                (8, b"neutron", -1.2, -0.8),
            ],
            dtype=primaries_dtype,
        )
        secondary_rows = self.np.array(
            [
                (7, 21, b"proton", 0.0, 0.0, 0.0, 4.250, 5.0, 1.0, 0.0),
                (7, 22, b"alpha", 1.0, 3.0, 0.0, 1.500, 1.0, 8.0, 2.0),
                (9, 41, b"proton", 2.0, 2.0, 0.0, 2.750, self.np.nan, 4.0, 0.0),
                (8, 31, b"proton", -1.0, -1.0, 0.0, 3.125, -2.0, -2.0, 0.0),
            ],
            dtype=secondaries_dtype,
        )
        photon_rows = self.np.array(
            [
                (7, 21, 1.0, 0.2, 0.0, 1.4, 0.5, 0.3),
                (7, 21, 3.5, 0.8, 0.0, 4.1, 1.2, 0.3),
                (7, 22, 1.1, 5.5, 1.0, 1.0, 6.2, 1.9),
                (9, 41, 2.3, 2.2, 0.0, 2.6, 2.4, 0.2),
                (9, 41, 2.7, 2.9, 0.0, self.np.nan, self.np.nan, self.np.nan),
                (8, 31, -1.5, -1.5, 0.0, -1.8, -1.9, 0.4),
            ],
            dtype=photons_dtype,
        )
        with self.h5py.File(path, "w") as handle:
            handle.create_dataset("primaries", data=primary_rows)
            handle.create_dataset("secondaries", data=secondary_rows)
            handle.create_dataset("photons", data=photon_rows)

    def _write_event_transport_hdf5(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        transported_dtype = self.np.dtype(
            [
                ("source_photon_index", self.np.int64),
                ("reached_intensifier", self.np.bool_),
            ]
        )
        rows = self.np.array(
            [
                (0, False),
                (1, True),
                (2, True),
                (3, False),
                (4, False),
                (5, True),
            ],
            dtype=transported_dtype,
        )
        with self.h5py.File(path, "w") as handle:
            handle.create_dataset("transported_photons", data=rows)
