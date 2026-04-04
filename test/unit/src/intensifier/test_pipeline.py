"""Unit tests for end-to-end intensifier pipeline execution."""

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


class IntensifierPipelineTests(unittest.TestCase):
    """Validate end-to-end stage composition for the intensifier module."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import h5py

            from src.common.hdf5_schema import DATASET_INTENSIFIER_OUTPUT_EVENTS
            from src.config.SimConfig import SimConfig
            from src.intensifier.models import IntensifierParams
            from src.intensifier.models import McpParams
            from src.intensifier.models import PhotocathodeParams
            from src.intensifier.models import PhosphorParams
            from src.intensifier.models import TransportedPhotonBatch
            from src.intensifier.pipeline import run_intensifier_pipeline
            from src.intensifier.pipeline import run_intensifier_pipeline_from_sim_config
        except ModuleNotFoundError as exc:
            missing = (getattr(exc, "name", "") or "").lower()
            if missing in {"numpy", "h5py", "pydantic"}:
                raise unittest.SkipTest(
                    f"Missing dependency for intensifier tests: {exc}. "
                    "Run in the project environment (for example: pixi run test-python)."
                ) from exc
            raise

        cls.h5py = h5py
        cls.DATASET_INTENSIFIER_OUTPUT_EVENTS = DATASET_INTENSIFIER_OUTPUT_EVENTS
        cls.SimConfig = SimConfig
        cls.IntensifierParams = IntensifierParams
        cls.McpParams = McpParams
        cls.PhotocathodeParams = PhotocathodeParams
        cls.PhosphorParams = PhosphorParams
        cls.TransportedPhotonBatch = TransportedPhotonBatch
        cls.run_intensifier_pipeline = staticmethod(run_intensifier_pipeline)
        cls.run_intensifier_pipeline_from_sim_config = staticmethod(
            run_intensifier_pipeline_from_sim_config
        )

    def _photons(self) -> object:
        """Build a small deterministic transported-photon batch."""

        return self.TransportedPhotonBatch(
            source_photon_index=np.array([0, 1, 2], dtype=np.int64),
            gun_call_id=np.array([10, 10, 11], dtype=np.int64),
            primary_track_id=np.array([100, 100, 101], dtype=np.int32),
            secondary_track_id=np.array([200, 201, 202], dtype=np.int32),
            photon_track_id=np.array([300, 301, 302], dtype=np.int32),
            x_mm=np.array([1.0, 2.0, 3.0], dtype=np.float64),
            y_mm=np.array([-1.0, -2.0, -3.0], dtype=np.float64),
            z_mm=np.array([0.5, 0.5, 0.5], dtype=np.float64),
            time_ns=np.array([5.0, 6.0, 7.0], dtype=np.float64),
            wavelength_nm=np.array([400.0, 500.0, 650.0], dtype=np.float64),
        )

    def _params(self) -> object:
        """Build a deterministic intensifier parameter bundle."""

        return self.IntensifierParams(
            photocathode=self.PhotocathodeParams(
                qe_wavelength_nm=np.array([350.0, 700.0], dtype=np.float64),
                qe_values=np.array([1.0, 1.0], dtype=np.float64),
                collection_efficiency=1.0,
                tts_sigma_ns=0.0,
            ),
            mcp=self.McpParams(
                stage1_mean_gain=10.0,
                stage1_gain_shape=2.0,
                stage2_mean_gain=100.0,
                stage2_gain_shape=2.0,
                gain_ref=1000.0,
                spread_sigma0_mm=0.0,
                spread_gain_exponent=0.4,
            ),
            phosphor=self.PhosphorParams(
                phosphor_gain=1.0,
                decay_fast_ns=70.0,
                decay_slow_ns=200.0,
                fast_fraction=1.0,
                psf_sigma_mm=0.0,
            ),
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
            "Metadata": {
                "author": "Unit Test",
                "date": "2026-03-19",
                "version": "test",
                "description": "Intensifier pipeline test payload.",
                "RunEnvironment": {
                    "SimulationRunID": "intensifier_pipeline_test",
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
        primaries_dtype = np.dtype(
            [
                ("gun_call_id", np.int64),
                ("primary_track_id", np.int32),
            ]
        )
        secondaries_dtype = np.dtype(
            [
                ("gun_call_id", np.int64),
                ("primary_track_id", np.int32),
                ("secondary_track_id", np.int32),
            ]
        )
        photons_dtype = np.dtype(
            [
                ("gun_call_id", np.int64),
                ("primary_track_id", np.int32),
                ("secondary_track_id", np.int32),
                ("photon_track_id", np.int32),
                ("optical_interface_hit_time_ns", np.float64),
                ("optical_interface_hit_wavelength_nm", np.float64),
            ]
        )
        photons = np.array(
            [
                (0, 1, 10, 100, 11.0, 450.0),
                (0, 1, 10, 101, 12.0, 500.0),
            ],
            dtype=photons_dtype,
        )
        primaries = np.array([(0, 1)], dtype=primaries_dtype)
        secondaries = np.array([(0, 1, 10)], dtype=secondaries_dtype)
        with self.h5py.File(path, "w") as handle:
            handle.create_dataset("primaries", data=primaries)
            handle.create_dataset("secondaries", data=secondaries)
            handle.create_dataset("photons", data=photons)

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
                ("reached_intensifier", np.bool_),
                ("in_bounds", np.bool_),
            ]
        )
        rows = np.array(
            [
                (0, 0, 1, 10, 100, 1.5, 2.5, 3.5, True, True),
                (1, 0, 1, 10, 101, 4.5, 5.5, 6.5, True, True),
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

    def test_run_intensifier_pipeline_preserves_batch_size_with_unit_detection(self) -> None:
        photons = self._photons()
        params = self._params()

        result = self.run_intensifier_pipeline(
            photons,
            params,
            rng=np.random.default_rng(123),
        )

        self.assertEqual(len(result), len(photons))
        np.testing.assert_array_equal(result.source_photon_index, photons.source_photon_index)
        np.testing.assert_array_equal(result.gun_call_id, photons.gun_call_id)
        np.testing.assert_array_equal(result.primary_track_id, photons.primary_track_id)
        np.testing.assert_array_equal(result.secondary_track_id, photons.secondary_track_id)
        np.testing.assert_array_equal(result.photon_track_id, photons.photon_track_id)
        self.assertTrue(np.all(result.output_time_ns >= photons.time_ns))
        self.assertTrue(np.all(result.signal_amplitude_arb > 0.0))

    def test_repeated_calls_can_reuse_one_parameter_bundle(self) -> None:
        photons = self._photons()
        params = self._params()
        result1 = self.run_intensifier_pipeline(
            photons,
            params,
            rng=np.random.default_rng(123),
        )
        result2 = self.run_intensifier_pipeline(
            photons,
            params,
            rng=np.random.default_rng(123),
        )

        self.assertEqual(len(result1), len(photons))
        self.assertEqual(len(result2), len(photons))
        np.testing.assert_array_equal(result1.source_photon_index, photons.source_photon_index)
        np.testing.assert_array_equal(result2.source_photon_index, photons.source_photon_index)
        np.testing.assert_allclose(result1.output_x_mm, result2.output_x_mm)
        np.testing.assert_allclose(result1.output_y_mm, result2.output_y_mm)
        np.testing.assert_allclose(result1.output_time_ns, result2.output_time_ns)

    def test_run_intensifier_pipeline_from_sim_config_loads_hdf5_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config = self.SimConfig.model_validate(self._config_payload(tmp_path))
            source_hdf5 = tmp_path / "simulatedPhotons" / "source.h5"
            transport_hdf5 = tmp_path / "transportedPhotons" / "transport.h5"
            self._write_source_hdf5(source_hdf5)
            self._write_transport_hdf5(transport_hdf5, source_hdf5=source_hdf5)

            result = self.run_intensifier_pipeline_from_sim_config(
                config,
                transport_hdf5_path=str(transport_hdf5),
                source_hdf5_path=str(source_hdf5),
                rng=np.random.default_rng(123),
            )

            self.assertEqual(len(result), 2)
            np.testing.assert_array_equal(
                result.source_photon_index,
                np.array([0, 1], dtype=np.int64),
            )
            self.assertTrue(np.all(result.output_time_ns >= np.array([11.0, 12.0])))
            self.assertTrue(np.all(result.signal_amplitude_arb > 0.0))

    def test_run_intensifier_pipeline_from_sim_config_optionally_writes_hdf5_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            payload = self._config_payload(tmp_path)
            payload["intensifier"]["writeOutputHdf5"] = True
            config = self.SimConfig.model_validate(payload)
            source_hdf5 = tmp_path / "simulatedPhotons" / "source.h5"
            transport_hdf5 = tmp_path / "transportedPhotons" / "transport.h5"
            expected_output = (
                tmp_path
                / "intensifier_pipeline_test"
                / "sensor"
                / "intensifier_output_events_0000.h5"
            )
            self._write_source_hdf5(source_hdf5)
            self._write_transport_hdf5(transport_hdf5, source_hdf5=source_hdf5)

            result = self.run_intensifier_pipeline_from_sim_config(
                config,
                transport_hdf5_path=transport_hdf5,
                source_hdf5_path=source_hdf5,
                rng=np.random.default_rng(123),
            )

            self.assertEqual(len(result), 2)
            self.assertTrue(expected_output.exists())
            with self.h5py.File(expected_output, "r") as handle:
                self.assertIn(self.DATASET_INTENSIFIER_OUTPUT_EVENTS, handle)
                dataset = handle[self.DATASET_INTENSIFIER_OUTPUT_EVENTS][:]
                self.assertEqual(len(dataset), 2)
                np.testing.assert_array_equal(
                    dataset["source_photon_index"],
                    result.source_photon_index,
                )
                np.testing.assert_allclose(dataset["output_x_mm"], result.output_x_mm)
                np.testing.assert_allclose(dataset["output_y_mm"], result.output_y_mm)
                np.testing.assert_allclose(dataset["output_time_ns"], result.output_time_ns)
                np.testing.assert_allclose(
                    dataset["signal_amplitude_arb"],
                    result.signal_amplitude_arb,
                )
                np.testing.assert_allclose(dataset["total_gain"], result.total_gain)
                np.testing.assert_allclose(dataset["wavelength_nm"], result.wavelength_nm)
                self.assertEqual(
                    handle.attrs["transport_hdf5"],
                    str(transport_hdf5.resolve()),
                )
                self.assertEqual(
                    handle.attrs["source_hdf5"],
                    str(source_hdf5.resolve()),
                )
                self.assertEqual(handle.attrs["run_id"], "intensifier_pipeline_test")
                self.assertEqual(handle.attrs["intensifier_model"], "Cricket2")
                self.assertIn("generated_utc", handle.attrs)


if __name__ == "__main__":
    unittest.main()
