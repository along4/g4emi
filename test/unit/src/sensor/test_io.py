"""Unit tests for Timepix sensor HDF5 I/O."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np


def _repo_root() -> Path:
    """Resolve repository root by searching parent directories."""

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src").is_dir() and (parent / "pixi.toml").is_file():
            return parent
    raise RuntimeError("Could not resolve repository root from test path.")


sys.path.insert(0, str(_repo_root()))


class TimepixIoTests(unittest.TestCase):
    """Validate sensor-stage HDF5 writing and config-derived output paths."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import h5py

            from src.common.hdf5_schema import DATASET_PRIMARIES
            from src.common.hdf5_schema import DATASET_SECONDARIES
            from src.config.SimConfig import SimConfig
            from src.sensor.io import DATASET_TIMEPIX_HITS
            from src.sensor.io import timepix_hit_batch_to_structured_array
            from src.sensor.io import timepix_hits_hdf5_path_from_sim_config
            from src.sensor.io import write_timepix_hits_hdf5
            from src.sensor.models import TimepixHitBatch
        except ModuleNotFoundError as exc:
            missing = (getattr(exc, "name", "") or "").lower()
            if missing in {"h5py", "numpy", "pydantic"}:
                raise unittest.SkipTest(
                    f"Missing dependency for sensor IO tests: {exc}. "
                    "Run in the project environment (for example: pixi run python -m unittest)."
                ) from exc
            raise

        cls.h5py = h5py
        cls.DATASET_PRIMARIES = DATASET_PRIMARIES
        cls.DATASET_SECONDARIES = DATASET_SECONDARIES
        cls.DATASET_TIMEPIX_HITS = DATASET_TIMEPIX_HITS
        cls.SimConfig = SimConfig
        cls.TimepixHitBatch = TimepixHitBatch
        cls.timepix_hit_batch_to_structured_array = staticmethod(
            timepix_hit_batch_to_structured_array
        )
        cls.timepix_hits_hdf5_path_from_sim_config = staticmethod(
            timepix_hits_hdf5_path_from_sim_config
        )
        cls.write_timepix_hits_hdf5 = staticmethod(write_timepix_hits_hdf5)

    def _base_payload(self, tmp_path: Path) -> dict[str, object]:
        """Build a minimal valid SimConfig payload for sensor I/O tests."""

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
            "sensor": {
                "model": "Timepix",
                "timepix": {
                    "pixelsX": 256,
                    "pixelsY": 256,
                    "pixelPitchMm": 0.055,
                    "maxTotNs": 25550.0,
                    "deadTimeNs": 475.0,
                },
            },
            "Metadata": {
                "author": "Unit Test",
                "date": "2026-04-04",
                "version": "test",
                "description": "Timepix IO test payload.",
                "RunEnvironment": {
                    "SimulationRunID": "timepix_io_test",
                    "SubRunNumber": 0,
                    "WorkingDirectory": str(tmp_path),
                    "MacroDirectory": "macros",
                    "LogDirectory": "logs",
                },
            },
        }

    def _hits(self) -> object:
        """Build a small deterministic Timepix hit batch."""

        return self.TimepixHitBatch(
            gun_call_id=np.array([10, 11], dtype=np.int64),
            primary_track_id=np.array([100, 101], dtype=np.int32),
            secondary_track_id=np.array([200, 201], dtype=np.int32),
            x_pixel=np.array([12, 13], dtype=np.int32),
            y_pixel=np.array([14, 15], dtype=np.int32),
            time_of_arrival_ns=np.array([0.0, 0.0], dtype=np.float64),
            time_over_threshold_ns=np.array([25.0, 50.0], dtype=np.float64),
            contribution_count=np.array([1, 3], dtype=np.int32),
        )

    def _write_source_hdf5(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        primaries_dtype = np.dtype([("gun_call_id", np.int64), ("primary_track_id", np.int32)])
        secondaries_dtype = np.dtype(
            [
                ("gun_call_id", np.int64),
                ("primary_track_id", np.int32),
                ("secondary_track_id", np.int32),
            ]
        )
        with self.h5py.File(path, "w") as handle:
            handle.create_dataset("primaries", data=np.array([(0, 1)], dtype=primaries_dtype))
            handle.create_dataset(
                "secondaries",
                data=np.array([(0, 1, 10)], dtype=secondaries_dtype),
            )
            handle.create_dataset(
                "photons",
                data=np.array(
                    [(0, 1, 10, 100, 11.0, 450.0)],
                    dtype=np.dtype(
                        [
                            ("gun_call_id", np.int64),
                            ("primary_track_id", np.int32),
                            ("secondary_track_id", np.int32),
                            ("photon_track_id", np.int32),
                            ("optical_interface_hit_time_ns", np.float64),
                            ("optical_interface_hit_wavelength_nm", np.float64),
                        ]
                    ),
                ),
            )

    def _write_transport_hdf5(self, path: Path, *, source_hdf5: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        transported_dtype = np.dtype(
            [
                ("source_photon_index", np.int64),
                ("gun_call_id", np.int64),
                ("primary_track_id", np.int32),
                ("secondary_track_id", np.int32),
                ("photon_track_id", np.int32),
                ("intensifier_hit_x_mm", np.float64),
                ("intensifier_hit_y_mm", np.float64),
                ("intensifier_hit_z_mm", np.float64),
                ("intensifier_hit_time_ns", np.float64),
                ("intensifier_hit_wavelength_nm", np.float64),
                ("in_bounds", np.bool_),
            ]
        )
        with self.h5py.File(path, "w") as handle:
            handle.create_dataset(
                "primaries",
                data=np.array([(0, 1)], dtype=np.dtype([("gun_call_id", np.int64), ("primary_track_id", np.int32)])),
            )
            handle.create_dataset(
                "secondaries",
                data=np.array(
                    [(0, 1, 10)],
                    dtype=np.dtype(
                        [
                            ("gun_call_id", np.int64),
                            ("primary_track_id", np.int32),
                            ("secondary_track_id", np.int32),
                        ]
                    ),
                ),
            )
            handle.create_dataset(
                "transported_photons",
                data=np.array(
                    [(0, 0, 1, 10, 100, 1.0, 2.0, 3.0, 11.0, 450.0, True)],
                    dtype=transported_dtype,
                ),
            )
            handle.attrs["source_hdf5"] = str(source_hdf5.resolve())

    def test_timepix_hits_hdf5_path_from_sim_config_uses_sensor_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self.SimConfig.model_validate(self._base_payload(tmp_path))

            output_path = self.timepix_hits_hdf5_path_from_sim_config(config)

            self.assertEqual(output_path.parent.name, "sensor")
            self.assertEqual(output_path.parent.parent.name, "timepix_io_test")
            self.assertEqual(output_path.name, "timepix_hits_0000.h5")

    def test_timepix_hit_batch_to_structured_array_uses_expected_fields(self) -> None:
        structured = self.timepix_hit_batch_to_structured_array(self._hits())

        self.assertEqual(
            structured.dtype.names,
            (
                "gun_call_id",
                "primary_track_id",
                "secondary_track_id",
                "x_pixel",
                "y_pixel",
                "time_of_arrival_ns",
                "time_over_threshold_ns",
                "contribution_count",
            ),
        )
        self.assertEqual(len(structured), 2)
        self.assertEqual(int(structured["x_pixel"][0]), 12)
        self.assertAlmostEqual(float(structured["time_over_threshold_ns"][1]), 50.0)

    def test_write_timepix_hits_hdf5_writes_dataset_and_attrs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self.SimConfig.model_validate(self._base_payload(tmp_path))
            source_hdf5 = tmp_path / "source.h5"
            transport_hdf5 = tmp_path / "transport.h5"
            output_hdf5 = tmp_path / "sensor" / "timepix_hits_0000.h5"
            self._write_source_hdf5(source_hdf5)
            self._write_transport_hdf5(transport_hdf5, source_hdf5=source_hdf5)

            written_path = self.write_timepix_hits_hdf5(
                self._hits(),
                config=config,
                transport_hdf5_path=transport_hdf5,
                source_hdf5_path=source_hdf5,
                output_hdf5_path=output_hdf5,
            )

            self.assertEqual(written_path, output_hdf5.resolve())
            with self.h5py.File(written_path, "r") as handle:
                self.assertIn(self.DATASET_PRIMARIES, handle)
                self.assertIn(self.DATASET_SECONDARIES, handle)
                self.assertIn(self.DATASET_TIMEPIX_HITS, handle)
                dataset = handle[self.DATASET_TIMEPIX_HITS][:]
                self.assertEqual(len(dataset), 2)
                self.assertEqual(
                    dataset.dtype.names,
                    (
                        "gun_call_id",
                        "primary_track_id",
                        "secondary_track_id",
                        "x_pixel",
                        "y_pixel",
                        "time_of_arrival_ns",
                        "time_over_threshold_ns",
                        "contribution_count",
                    ),
                )
                np.testing.assert_array_equal(dataset["gun_call_id"], np.array([10, 11], dtype=np.int64))
                np.testing.assert_array_equal(dataset["x_pixel"], np.array([12, 13], dtype=np.int32))
                np.testing.assert_allclose(
                    dataset["time_over_threshold_ns"],
                    np.array([25.0, 50.0], dtype=np.float64),
                )
                self.assertEqual(handle.attrs["run_id"], "timepix_io_test")
                self.assertEqual(handle.attrs["intensifier_model"], "Cricket2")
                self.assertEqual(handle.attrs["sensor_model"], "Timepix")
                self.assertEqual(handle.attrs["transport_hdf5"], str(transport_hdf5.resolve()))
                self.assertEqual(handle.attrs["source_hdf5"], str(source_hdf5.resolve()))
                self.assertIn("generated_utc", handle.attrs)

    def test_write_timepix_hits_hdf5_writes_empty_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self.SimConfig.model_validate(self._base_payload(tmp_path))
            source_hdf5 = tmp_path / "source.h5"
            transport_hdf5 = tmp_path / "transport.h5"
            output_hdf5 = tmp_path / "sensor" / "timepix_hits_0000.h5"
            self._write_source_hdf5(source_hdf5)
            self._write_transport_hdf5(transport_hdf5, source_hdf5=source_hdf5)

            written_path = self.write_timepix_hits_hdf5(
                self.TimepixHitBatch.empty(),
                config=config,
                transport_hdf5_path=transport_hdf5,
                source_hdf5_path=source_hdf5,
                output_hdf5_path=output_hdf5,
            )

            with self.h5py.File(written_path, "r") as handle:
                self.assertIn(self.DATASET_TIMEPIX_HITS, handle)
                dataset = handle[self.DATASET_TIMEPIX_HITS][:]
                self.assertEqual(len(dataset), 0)
                self.assertEqual(dataset.dtype.names[0], "gun_call_id")


if __name__ == "__main__":
    unittest.main()
