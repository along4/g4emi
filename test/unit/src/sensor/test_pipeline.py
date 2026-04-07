"""Unit tests for end-to-end Timepix pipeline execution."""

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


class TimepixPipelineTests(unittest.TestCase):
    """Validate sensor-stage composition and config-driven execution."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import h5py

            from src.config.SimConfig import SimConfig
            from src.intensifier.models import IntensifierOutputBatch
            from src.sensor.io import DATASET_TIMEPIX_HITS
            from src.sensor.models import TimepixParams
            from src.sensor.pipeline import run_timepix_pipeline
            from src.sensor.pipeline import run_timepix_pipeline_from_sim_config
        except ModuleNotFoundError as exc:
            missing = (getattr(exc, "name", "") or "").lower()
            if missing in {"h5py", "numpy", "pydantic"}:
                raise unittest.SkipTest(
                    f"Missing dependency for sensor pipeline tests: {exc}. "
                    "Run in the project environment (for example: pixi run python -m unittest)."
                ) from exc
            raise

        cls.h5py = h5py
        cls.SimConfig = SimConfig
        cls.IntensifierOutputBatch = IntensifierOutputBatch
        cls.DATASET_TIMEPIX_HITS = DATASET_TIMEPIX_HITS
        cls.TimepixParams = TimepixParams
        cls.run_timepix_pipeline = staticmethod(run_timepix_pipeline)
        cls.run_timepix_pipeline_from_sim_config = staticmethod(
            run_timepix_pipeline_from_sim_config
        )

    def _intensifier_output(self) -> object:
        """Build a small deterministic intensifier output batch."""

        return self.IntensifierOutputBatch(
            source_photon_index=np.array([0, 1, 2], dtype=np.int64),
            gun_call_id=np.array([10, 10, 11], dtype=np.int64),
            primary_track_id=np.array([100, 100, 101], dtype=np.int32),
            secondary_track_id=np.array([200, 201, 202], dtype=np.int32),
            photon_track_id=np.array([300, 301, 302], dtype=np.int32),
            output_x_mm=np.array([0.0, 0.0, 10.0], dtype=np.float64),
            output_y_mm=np.array([0.0, 0.0, 0.0], dtype=np.float64),
            output_time_ns=np.array([10.0, 12.0, 20.0], dtype=np.float64),
            signal_amplitude_arb=np.array([5.0, 4.0, 3.0], dtype=np.float64),
            total_gain=np.array([100.0, 80.0, 60.0], dtype=np.float64),
            wavelength_nm=np.array([400.0, 500.0, 600.0], dtype=np.float64),
        )

    def _config_payload(self, working_directory: Path) -> dict[str, object]:
        """Build a minimal valid SimConfig payload for HDF5-driven pipeline tests."""

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
                "photocathode": {
                    "qeWavelengthNm": [350.0, 700.0],
                    "qeValues": [1.0, 1.0],
                    "collectionEfficiency": 1.0,
                    "ttsSigmaNs": 0.0,
                },
                "mcp": {
                    "stage1MeanGain": 10.0,
                    "stage1GainShape": 2.0,
                    "stage2MeanGain": 100.0,
                    "stage2GainShape": 2.0,
                    "gainRef": 1000.0,
                    "spreadSigma0Mm": 0.0,
                    "spreadGainExponent": 0.4,
                },
                "phosphor": {
                    "phosphorGain": 1.0,
                    "decayFastNs": 70.0,
                    "decaySlowNs": 200.0,
                    "fastFraction": 1.0,
                    "psfSigmaMm": 0.0,
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
                "description": "Timepix pipeline test payload.",
                "RunEnvironment": {
                    "SimulationRunID": "timepix_pipeline_test",
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
                "photons",
                data=np.array(
                    [
                        (0, 1, 10, 100, 11.0, 450.0),
                        (0, 1, 10, 101, 12.0, 500.0),
                    ],
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

    def _write_transport_hdf5(
        self,
        path: Path,
        *,
        source_hdf5: Path,
        hit_x_mm: float = 0.0,
        hit_y_mm: float = 0.0,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
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
                    [
                        (0, 0, 1, 10, 100, hit_x_mm, hit_y_mm, 0.0, 11.0, 450.0, True),
                        (1, 0, 1, 10, 101, hit_x_mm, hit_y_mm, 0.0, 12.0, 500.0, True),
                    ],
                    dtype=np.dtype(
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
                    ),
                ),
            )
            handle.attrs["source_hdf5"] = str(source_hdf5.resolve())

    def test_run_timepix_pipeline_maps_and_merges_events(self) -> None:
        params = self.TimepixParams(
            pixels_x=256,
            pixels_y=256,
            pixel_pitch_mm=0.055,
            max_tot_ns=20.0,
            dead_time_ns=5.0,
        )

        result = self.run_timepix_pipeline(self._intensifier_output(), params)

        self.assertEqual(len(result), 1)
        self.assertEqual(int(result.gun_call_id[0]), 10)
        self.assertEqual(int(result.contribution_count[0]), 2)
        self.assertAlmostEqual(float(result.time_over_threshold_ns[0]), 7.0)

    def test_run_timepix_pipeline_from_sim_config_writes_hdf5_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self.SimConfig.model_validate(self._config_payload(tmp_path))
            source_hdf5 = tmp_path / "simulatedPhotons" / "source.h5"
            transport_hdf5 = tmp_path / "transportedPhotons" / "transport.h5"
            expected_output = (
                tmp_path
                / "timepix_pipeline_test"
                / "sensor"
                / "timepix_hits_0000.h5"
            )
            self._write_source_hdf5(source_hdf5)
            self._write_transport_hdf5(transport_hdf5, source_hdf5=source_hdf5)

            result = self.run_timepix_pipeline_from_sim_config(
                config,
                transport_hdf5_path=transport_hdf5,
                source_hdf5_path=source_hdf5,
            )

            self.assertEqual(len(result), 1)
            self.assertTrue(expected_output.exists())
            with self.h5py.File(expected_output, "r") as handle:
                self.assertIn(self.DATASET_TIMEPIX_HITS, handle)
                dataset = handle[self.DATASET_TIMEPIX_HITS][:]
                self.assertEqual(len(dataset), 1)
                np.testing.assert_array_equal(dataset["gun_call_id"], result.gun_call_id)
                np.testing.assert_array_equal(dataset["x_pixel"], result.x_pixel)
                np.testing.assert_array_equal(dataset["y_pixel"], result.y_pixel)
                np.testing.assert_allclose(
                    dataset["time_over_threshold_ns"],
                    result.time_over_threshold_ns,
                )
                np.testing.assert_array_equal(
                    dataset["contribution_count"],
                    result.contribution_count,
                )
                self.assertEqual(handle.attrs["run_id"], "timepix_pipeline_test")
                self.assertEqual(handle.attrs["intensifier_model"], "Cricket2")
                self.assertEqual(handle.attrs["sensor_model"], "Timepix")
                self.assertEqual(
                    handle.attrs["transport_hdf5"],
                    str(transport_hdf5.resolve()),
                )
                self.assertEqual(
                    handle.attrs["source_hdf5"],
                    str(source_hdf5.resolve()),
                )
                self.assertIn("generated_utc", handle.attrs)

    def test_run_timepix_pipeline_from_sim_config_writes_empty_output_when_no_hits_survive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            payload = self._config_payload(tmp_path)
            payload["sensor"]["timepix"]["pixelsX"] = 1
            payload["sensor"]["timepix"]["pixelsY"] = 1
            payload["sensor"]["timepix"]["pixelPitchMm"] = 0.01
            config = self.SimConfig.model_validate(payload)
            source_hdf5 = tmp_path / "simulatedPhotons" / "source.h5"
            transport_hdf5 = tmp_path / "transportedPhotons" / "transport.h5"
            expected_output = (
                tmp_path
                / "timepix_pipeline_test"
                / "sensor"
                / "timepix_hits_0000.h5"
            )
            self._write_source_hdf5(source_hdf5)
            self._write_transport_hdf5(
                transport_hdf5,
                source_hdf5=source_hdf5,
                hit_x_mm=1.0,
                hit_y_mm=1.0,
            )

            result = self.run_timepix_pipeline_from_sim_config(
                config,
                transport_hdf5_path=transport_hdf5,
                source_hdf5_path=source_hdf5,
            )

            self.assertEqual(len(result), 0)
            self.assertTrue(expected_output.exists())
            with self.h5py.File(expected_output, "r") as handle:
                self.assertIn(self.DATASET_TIMEPIX_HITS, handle)
                self.assertEqual(len(handle[self.DATASET_TIMEPIX_HITS]), 0)


if __name__ == "__main__":
    unittest.main()
