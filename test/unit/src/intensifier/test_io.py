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

            from src.common.hdf5_schema import DATASET_INTENSIFIER_OUTPUT_EVENTS
            from src.common.hdf5_schema import DATASET_PRIMARIES
            from src.common.hdf5_schema import DATASET_SECONDARIES
            from src.intensifier.io import load_transported_photon_batch
            from src.intensifier.io import load_transported_photon_batch_from_sim_config
            from src.intensifier.io import intensifier_output_batch_to_structured_array
            from src.intensifier.io import intensifier_output_hdf5_path_from_sim_config
            from src.intensifier.io import resolve_intensifier_input_hdf5_paths
            from src.intensifier.io import write_intensifier_output_hdf5
            from src.intensifier.models import IntensifierOutputBatch
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
        cls.DATASET_INTENSIFIER_OUTPUT_EVENTS = DATASET_INTENSIFIER_OUTPUT_EVENTS
        cls.DATASET_PRIMARIES = DATASET_PRIMARIES
        cls.DATASET_SECONDARIES = DATASET_SECONDARIES
        cls.IntensifierOutputBatch = IntensifierOutputBatch
        cls.load_transported_photon_batch = staticmethod(load_transported_photon_batch)
        cls.load_transported_photon_batch_from_sim_config = staticmethod(
            load_transported_photon_batch_from_sim_config
        )
        cls.intensifier_output_batch_to_structured_array = staticmethod(
            intensifier_output_batch_to_structured_array
        )
        cls.intensifier_output_hdf5_path_from_sim_config = staticmethod(
            intensifier_output_hdf5_path_from_sim_config
        )
        cls.resolve_intensifier_input_hdf5_paths = staticmethod(
            resolve_intensifier_input_hdf5_paths
        )
        cls.write_intensifier_output_hdf5 = staticmethod(write_intensifier_output_hdf5)
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
        primaries_dtype = self.np.dtype(
            [
                ("gun_call_id", self.np.int64),
                ("primary_track_id", self.np.int32),
            ]
        )
        secondaries_dtype = self.np.dtype(
            [
                ("gun_call_id", self.np.int64),
                ("primary_track_id", self.np.int32),
                ("secondary_track_id", self.np.int32),
            ]
        )
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
        primaries = self.np.array([(0, 1)], dtype=primaries_dtype)
        secondaries = self.np.array([(0, 1, 10)], dtype=secondaries_dtype)
        with self.h5py.File(path, "w") as handle:
            handle.create_dataset("primaries", data=primaries)
            handle.create_dataset("secondaries", data=secondaries)
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
            if source_hdf5.exists():
                with self.h5py.File(source_hdf5, "r") as source_handle:
                    if "primaries" in source_handle:
                        source_handle.copy("primaries", handle)
                    if "secondaries" in source_handle:
                        source_handle.copy("secondaries", handle)
            handle.create_dataset("transported_photons", data=rows)
            handle.attrs["source_hdf5"] = str(source_hdf5.resolve())

    def _output_events(self) -> object:
        return self.IntensifierOutputBatch(
            source_photon_index=self.np.array([0, 1], dtype=self.np.int64),
            gun_call_id=self.np.array([0, 0], dtype=self.np.int64),
            primary_track_id=self.np.array([1, 1], dtype=self.np.int32),
            secondary_track_id=self.np.array([10, 10], dtype=self.np.int32),
            photon_track_id=self.np.array([100, 101], dtype=self.np.int32),
            output_x_mm=self.np.array([1.25, 4.5], dtype=self.np.float64),
            output_y_mm=self.np.array([2.5, 5.75], dtype=self.np.float64),
            output_time_ns=self.np.array([12.0, 13.5], dtype=self.np.float64),
            signal_amplitude_arb=self.np.array([1000.0, 1250.0], dtype=self.np.float64),
            total_gain=self.np.array([1000.0, 1250.0], dtype=self.np.float64),
            wavelength_nm=self.np.array([450.0, 500.0], dtype=self.np.float64),
        )

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
            source_hdf5 = (
                tmp_path / "simulatedPhotons" / "photon_optical_interface_hits_0000.h5"
            )
            transport_hdf5 = (
                tmp_path / "transportedPhotons" / "photons_intensifier_hits_0000.h5"
            )
            self._write_source_hdf5(source_hdf5)
            self._write_transport_hdf5(transport_hdf5, source_hdf5=source_hdf5)

            transport_paths = self.resolve_intensifier_input_hdf5_paths(
                config,
                transport_hdf5_path=transport_hdf5,
                source_hdf5_path=source_hdf5,
            )
            self.assertEqual(transport_paths[0], transport_hdf5.resolve())
            self.assertEqual(transport_paths[1], source_hdf5.resolve())

            batch = self.load_transported_photon_batch_from_sim_config(
                config,
                transport_hdf5_path=transport_hdf5,
                source_hdf5_path=source_hdf5,
            )

            self.assertEqual(len(batch), 1)
            self.assertEqual(int(batch.photon_track_id[0]), 100)

    def test_intensifier_output_hdf5_path_from_sim_config_uses_sensor_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self.SimConfig.model_validate(self._base_payload(tmp_path))

            output_path = self.intensifier_output_hdf5_path_from_sim_config(config)

            self.assertEqual(output_path.parent.name, "sensor")
            self.assertEqual(output_path.parent.parent.name, "intensifier_io_test")
            self.assertEqual(output_path.name, "intensifier_output_events_0000.h5")

    def test_intensifier_output_batch_to_structured_array_uses_expected_fields(self) -> None:
        structured = self.intensifier_output_batch_to_structured_array(self._output_events())

        self.assertEqual(
            structured.dtype.names,
            (
                "source_photon_index",
                "gun_call_id",
                "primary_track_id",
                "secondary_track_id",
                "photon_track_id",
                "output_x_mm",
                "output_y_mm",
                "output_time_ns",
                "signal_amplitude_arb",
                "total_gain",
                "wavelength_nm",
            ),
        )
        self.assertEqual(len(structured), 2)
        self.assertAlmostEqual(float(structured["output_x_mm"][0]), 1.25)
        self.assertAlmostEqual(float(structured["signal_amplitude_arb"][1]), 1250.0)
        self.assertEqual(int(structured["photon_track_id"][1]), 101)

    def test_write_intensifier_output_hdf5_writes_dataset_and_attrs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self.SimConfig.model_validate(self._base_payload(tmp_path))
            source_hdf5 = tmp_path / "source.h5"
            transport_hdf5 = tmp_path / "transport.h5"
            output_hdf5 = tmp_path / "sensor" / "intensifier_output_events_0000.h5"
            self._write_source_hdf5(source_hdf5)
            self._write_transport_hdf5(transport_hdf5, source_hdf5=source_hdf5)

            written_path = self.write_intensifier_output_hdf5(
                self._output_events(),
                config=config,
                transport_hdf5_path=transport_hdf5,
                output_hdf5_path=output_hdf5,
            )

            self.assertEqual(written_path, output_hdf5.resolve())
            with self.h5py.File(written_path, "r") as handle:
                self.assertIn(self.DATASET_PRIMARIES, handle)
                self.assertIn(self.DATASET_SECONDARIES, handle)
                self.assertIn(self.DATASET_INTENSIFIER_OUTPUT_EVENTS, handle)
                dataset = handle[self.DATASET_INTENSIFIER_OUTPUT_EVENTS][:]
                self.assertEqual(len(dataset), 2)
                self.assertEqual(
                    dataset.dtype.names,
                    (
                        "source_photon_index",
                        "gun_call_id",
                        "primary_track_id",
                        "secondary_track_id",
                        "photon_track_id",
                        "output_x_mm",
                        "output_y_mm",
                        "output_time_ns",
                        "signal_amplitude_arb",
                        "total_gain",
                        "wavelength_nm",
                    ),
                )
                self.np.testing.assert_array_equal(
                    dataset["source_photon_index"],
                    self.np.array([0, 1], dtype=self.np.int64),
                )
                self.np.testing.assert_allclose(
                    dataset["output_x_mm"],
                    self.np.array([1.25, 4.5], dtype=self.np.float64),
                )
                self.np.testing.assert_allclose(
                    dataset["output_time_ns"],
                    self.np.array([12.0, 13.5], dtype=self.np.float64),
                )
                self.np.testing.assert_allclose(
                    dataset["signal_amplitude_arb"],
                    self.np.array([1000.0, 1250.0], dtype=self.np.float64),
                )
                self.assertEqual(len(handle[self.DATASET_PRIMARIES]), 1)
                self.assertEqual(len(handle[self.DATASET_SECONDARIES]), 1)
                self.assertEqual(handle.attrs["run_id"], "intensifier_io_test")
                self.assertEqual(handle.attrs["intensifier_model"], "Cricket2")
                self.assertEqual(handle.attrs["transport_hdf5"], str(transport_hdf5.resolve()))
                self.assertEqual(handle.attrs["source_hdf5"], str(source_hdf5.resolve()))
                self.assertIn("generated_utc", handle.attrs)


if __name__ == "__main__":
    unittest.main()
