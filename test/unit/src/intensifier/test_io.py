"""Unit tests for intensifier HDF5 I/O helpers."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


def _repo_root() -> Path:
    """Resolve repository root by searching parent directories."""

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src").is_dir() and (parent / "pixi.toml").is_file():
            return parent
    raise RuntimeError("Could not resolve repository root from test path.")


sys.path.insert(0, str(_repo_root()))


class IntensifierIoTests(unittest.TestCase):
    """Validate loading of intensifier input batches from HDF5."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import h5py
            import numpy as np

            from src.intensifier.io import load_transported_photon_batch
            from src.intensifier.io import load_transported_photon_batch_from_sim_config
            from src.intensifier.io import resolve_intensifier_input_hdf5_paths
            from src.config.SimConfig import SimConfig
        except ModuleNotFoundError as exc:
            missing = (getattr(exc, "name", "") or "").lower()
            if missing in {"h5py", "numpy", "pydantic"}:
                raise unittest.SkipTest(
                    f"Missing dependency for intensifier I/O tests: {exc}. "
                    "Run in the project environment (for example: pixi run test-python)."
                ) from exc
            raise

        cls.h5py = h5py
        cls.np = np
        cls.load_transported_photon_batch = staticmethod(load_transported_photon_batch)
        cls.load_transported_photon_batch_from_sim_config = staticmethod(
            load_transported_photon_batch_from_sim_config
        )
        cls.resolve_intensifier_input_hdf5_paths = staticmethod(
            resolve_intensifier_input_hdf5_paths
        )
        cls.SimConfig = SimConfig

    def _base_payload(self, working_directory: Path) -> dict[str, object]:
        return {
            "scintillator": {
                "catalogId": "EJ200",
                "position_mm": {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0},
                "dimension_mm": {"x_mm": 50.0, "y_mm": 50.0, "z_mm": 10.0},
                "properties": {
                    "name": "EJ200",
                    "photonEnergy": [2.0, 2.4, 2.76],
                    "rIndex": [1.58, 1.58, 1.58],
                    "nKEntries": 3,
                    "timeComponents": {
                        "default": [
                            {"timeConstant": 2.1, "yieldFraction": 1.0},
                            {"timeConstant": 0.0, "yieldFraction": 0.0},
                            {"timeConstant": 0.0, "yieldFraction": 0.0},
                        ]
                    },
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
                        "name": "CanonEF50mmf1.0L",
                        "primary": True,
                        "zmxFile": "CanonEF50mmf1.0L.zmx",
                    }
                ],
                "geometry": {"entranceDiameter": 60.55, "sensorMaxWidth": 36.0},
                "sensitiveDetectorConfig": {
                    "position_mm": {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 210.05},
                    "shape": "circle",
                    "diameterRule": "min(entranceDiameter,sensorMaxWidth)",
                },
            },
            "intensifier": {
                "model": "Cricket2",
                "input_screen": {
                    "image_circle_diameter_mm": 18.0,
                    "center_mm": [0.0, 0.0],
                    "magnification": 1.0,
                },
            },
            "Metadata": {
                "author": "Unit Test",
                "date": "2026-03-19",
                "version": "test",
                "description": "Intensifier IO test payload.",
                "RunEnvironment": {
                    "SimulationRunID": "intensifier_io_test",
                    "SubRunNumber": 0,
                    "WorkingDirectory": str(working_directory),
                    "MacroDirectory": "macros",
                    "LogDirectory": "logs",
                    "OutputInfo": {
                        "SimulatedPhotonsDirectory": "simulatedPhotons",
                        "TransportedPhotonsDirectory": "transportedPhotons",
                    },
                },
            },
        }

    def _write_source_hdf5(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        photons_dtype = self.np.dtype(
            [
                ("gun_call_id", self.np.int64),
                ("primary_track_id", self.np.int32),
                ("secondary_track_id", self.np.int32),
                ("photon_track_id", self.np.int32),
                ("optical_interface_hit_time_ns", self.np.float64),
                ("optical_interface_hit_wavelength_nm", self.np.float64),
            ]
        )
        photons = self.np.array(
            [
                (0, 1, 10, 100, 11.0, 450.0),
                (0, 1, 10, 101, 12.0, 500.0),
                (0, 1, 10, 102, 13.0, 550.0),
            ],
            dtype=photons_dtype,
        )
        with self.h5py.File(path, "w") as handle:
            handle.create_dataset("photons", data=photons)

    def _write_transport_hdf5(self, path: Path, *, source_hdf5: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        transported_dtype = self.np.dtype(
            [
                ("source_photon_index", self.np.int64),
                ("gun_call_id", self.np.int64),
                ("primary_track_id", self.np.int32),
                ("secondary_track_id", self.np.int32),
                ("photon_track_id", self.np.int32),
                ("intensifier_hit_x_mm", self.np.float64),
                ("intensifier_hit_y_mm", self.np.float64),
                ("intensifier_hit_z_mm", self.np.float64),
                ("reached_intensifier", self.np.bool_),
                ("in_bounds", self.np.bool_),
            ]
        )
        rows = self.np.array(
            [
                (0, 0, 1, 10, 100, 1.5, 2.5, 3.5, True, True),
                (1, 0, 1, 10, 101, 4.5, 5.5, 6.5, True, False),
                (2, 0, 1, 10, 102, self.np.nan, self.np.nan, self.np.nan, False, False),
            ],
            dtype=transported_dtype,
        )
        with self.h5py.File(path, "w") as handle:
            handle.create_dataset("transported_photons", data=rows)
            handle.attrs["source_hdf5"] = str(source_hdf5.resolve())

    def test_load_transported_photon_batch_filters_to_in_bounds_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_hdf5 = tmp_path / "source.h5"
            transport_hdf5 = tmp_path / "transport.h5"
            self._write_source_hdf5(source_hdf5)
            self._write_transport_hdf5(transport_hdf5, source_hdf5=source_hdf5)

            batch = self.load_transported_photon_batch(transport_hdf5)

            self.assertEqual(len(batch), 1)
            self.assertEqual(int(batch.source_photon_index[0]), 0)
            self.assertAlmostEqual(float(batch.x_mm[0]), 1.5)
            self.assertAlmostEqual(float(batch.y_mm[0]), 2.5)
            self.assertAlmostEqual(float(batch.z_mm[0]), 3.5)
            self.assertAlmostEqual(float(batch.time_ns[0]), 11.0)
            self.assertAlmostEqual(float(batch.wavelength_nm[0]), 450.0)

    def test_load_transported_photon_batch_can_include_out_of_bounds_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_hdf5 = tmp_path / "source.h5"
            transport_hdf5 = tmp_path / "transport.h5"
            self._write_source_hdf5(source_hdf5)
            self._write_transport_hdf5(transport_hdf5, source_hdf5=source_hdf5)

            batch = self.load_transported_photon_batch(
                transport_hdf5,
                require_in_bounds=False,
            )

            self.assertEqual(len(batch), 2)
            self.np.testing.assert_array_equal(
                batch.source_photon_index,
                self.np.array([0, 1], dtype=self.np.int64),
            )
            self.np.testing.assert_allclose(
                batch.time_ns,
                self.np.array([11.0, 12.0], dtype=self.np.float64),
            )

    def test_load_transported_photon_batch_from_sim_config_resolves_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self.SimConfig.model_validate(self._base_payload(tmp_path))
            transport_paths = self.resolve_intensifier_input_hdf5_paths(
                config,
                transport_hdf5_path=tmp_path / "transportedPhotons" / "photons_intensifier_hits_0000.h5",
                source_hdf5_path=tmp_path / "simulatedPhotons" / "photon_optical_interface_hits_0000.h5",
            )
            source_hdf5, transport_hdf5 = transport_paths[1], transport_paths[0]
            self._write_source_hdf5(source_hdf5)
            self._write_transport_hdf5(transport_hdf5, source_hdf5=source_hdf5)

            batch = self.load_transported_photon_batch_from_sim_config(
                config,
                transport_hdf5_path=transport_hdf5,
                source_hdf5_path=source_hdf5,
            )

            self.assertEqual(len(batch), 1)
            self.assertEqual(int(batch.photon_track_id[0]), 100)


if __name__ == "__main__":
    unittest.main()
