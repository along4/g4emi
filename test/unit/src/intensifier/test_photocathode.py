"""Unit tests for the intensifier photocathode stage."""

from __future__ import annotations

from pathlib import Path
import sys
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


class PhotocathodeStageTests(unittest.TestCase):
    """Validate QE interpolation and photoelectron generation."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from src.config.SimConfig import SimConfig
            from src.intensifier.models import PhotocathodeParams
            from src.intensifier.models import TransportedPhotonBatch
            from src.intensifier.photocathode import convert_photons_to_photoelectrons
            from src.intensifier.photocathode import interpolate_qe
            from src.intensifier.photocathode import photocathode_params_from_sim_config
        except ModuleNotFoundError as exc:
            missing = (getattr(exc, "name", "") or "").lower()
            if missing in {"pydantic", "numpy"}:
                raise unittest.SkipTest(
                    f"Missing dependency for intensifier tests: {exc}. "
                    "Run in the project environment (for example: pixi run test-python)."
                ) from exc
            raise
        cls.SimConfig = SimConfig
        cls.PhotocathodeParams = PhotocathodeParams
        cls.TransportedPhotonBatch = TransportedPhotonBatch
        cls.convert_photons_to_photoelectrons = staticmethod(
            convert_photons_to_photoelectrons
        )
        cls.interpolate_qe = staticmethod(interpolate_qe)
        cls.photocathode_params_from_sim_config = staticmethod(
            photocathode_params_from_sim_config
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

    def _config_payload(self) -> dict[str, object]:
        """Build a minimal valid SimConfig payload with intensifier parameters."""

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
                    "qeWavelengthNm": [350.0, 500.0, 650.0],
                    "qeValues": [0.1, 0.2, 0.05],
                    "collectionEfficiency": 0.8,
                    "ttsSigmaNs": 0.15,
                },
            },
            "Metadata": {
                "author": "Unit Test",
                "date": "2026-03-19",
                "version": "test",
                "description": "Photocathode stage test payload.",
                "RunEnvironment": {
                    "SimulationRunID": "photocathode_stage_test",
                    "WorkingDirectory": "data",
                    "MacroDirectory": "macros",
                    "LogDirectory": "logs",
                },
            },
        }

    def test_interpolate_qe_returns_zero_outside_range(self) -> None:
        params = self.PhotocathodeParams(
            qe_wavelength_nm=np.array([400.0, 500.0, 600.0], dtype=np.float64),
            qe_values=np.array([0.1, 0.4, 0.2], dtype=np.float64),
            collection_efficiency=1.0,
            tts_sigma_ns=0.0,
        )

        result = self.interpolate_qe(
            np.array([350.0, 400.0, 450.0, 650.0], dtype=np.float64),
            params,
        )

        np.testing.assert_allclose(
            result,
            np.array([0.0, 0.1, 0.25, 0.0], dtype=np.float64),
        )

    def test_convert_photons_to_photoelectrons_rejects_all_when_qe_is_zero(self) -> None:
        params = self.PhotocathodeParams(
            qe_wavelength_nm=np.array([400.0, 500.0], dtype=np.float64),
            qe_values=np.array([0.0, 0.0], dtype=np.float64),
            collection_efficiency=1.0,
            tts_sigma_ns=0.0,
        )

        result = self.convert_photons_to_photoelectrons(
            self._photons(),
            params,
            rng=np.random.default_rng(123),
        )

        self.assertEqual(len(result), 0)

    def test_convert_photons_to_photoelectrons_keeps_all_when_detection_probability_is_one(self) -> None:
        photons = self._photons()
        params = self.PhotocathodeParams(
            qe_wavelength_nm=np.array([350.0, 700.0], dtype=np.float64),
            qe_values=np.array([1.0, 1.0], dtype=np.float64),
            collection_efficiency=1.0,
            tts_sigma_ns=0.0,
        )

        result = self.convert_photons_to_photoelectrons(
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
        np.testing.assert_allclose(result.x_pc_mm, photons.x_mm)
        np.testing.assert_allclose(result.y_pc_mm, photons.y_mm)
        np.testing.assert_allclose(result.time_pc_ns, photons.time_ns)
        np.testing.assert_allclose(result.wavelength_nm, photons.wavelength_nm)

    def test_convert_photons_to_photoelectrons_adds_timing_jitter_when_enabled(self) -> None:
        photons = self._photons()
        params = self.PhotocathodeParams(
            qe_wavelength_nm=np.array([350.0, 700.0], dtype=np.float64),
            qe_values=np.array([1.0, 1.0], dtype=np.float64),
            collection_efficiency=1.0,
            tts_sigma_ns=0.5,
        )

        result = self.convert_photons_to_photoelectrons(
            photons,
            params,
            rng=np.random.default_rng(123),
        )

        self.assertEqual(len(result), len(photons))
        self.assertFalse(np.allclose(result.time_pc_ns, photons.time_ns))

    def test_photocathode_params_can_be_built_from_sim_config(self) -> None:
        config = self.SimConfig.model_validate(self._config_payload())
        params = self.photocathode_params_from_sim_config(config)

        np.testing.assert_allclose(
            params.qe_wavelength_nm,
            np.array([350.0, 500.0, 650.0], dtype=np.float64),
        )
        np.testing.assert_allclose(
            params.qe_values,
            np.array([0.1, 0.2, 0.05], dtype=np.float64),
        )
        self.assertAlmostEqual(params.collection_efficiency, 0.8)
        self.assertAlmostEqual(params.tts_sigma_ns, 0.15)


if __name__ == "__main__":
    unittest.main()
