"""Unit tests for the intensifier MCP stage."""

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


class McpStageTests(unittest.TestCase):
    """Validate MCP gain sampling, spread, and config integration."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from src.intensifier.mcp import compute_mcp_spread_sigma_mm
            from src.intensifier.mcp import convert_photoelectrons_to_mcp_events
            from src.intensifier.mcp import mcp_params_from_sim_config
            from src.intensifier.models import McpParams
            from src.intensifier.models import PhotoelectronBatch
        except ModuleNotFoundError as exc:
            missing = (getattr(exc, "name", "") or "").lower()
            if missing in {"numpy"}:
                raise unittest.SkipTest(
                    f"Missing dependency for intensifier tests: {exc}. "
                    "Run in the project environment (for example: pixi run test-python)."
                ) from exc
            raise

        cls.compute_mcp_spread_sigma_mm = staticmethod(compute_mcp_spread_sigma_mm)
        cls.convert_photoelectrons_to_mcp_events = staticmethod(
            convert_photoelectrons_to_mcp_events
        )
        cls.mcp_params_from_sim_config = staticmethod(mcp_params_from_sim_config)
        cls.McpParams = McpParams
        cls.PhotoelectronBatch = PhotoelectronBatch

    def _photoelectrons(self) -> object:
        """Build a small deterministic photoelectron batch."""

        return self.PhotoelectronBatch(
            source_photon_index=np.array([0, 1, 2], dtype=np.int64),
            gun_call_id=np.array([10, 10, 11], dtype=np.int64),
            primary_track_id=np.array([100, 100, 101], dtype=np.int32),
            secondary_track_id=np.array([200, 201, 202], dtype=np.int32),
            photon_track_id=np.array([300, 301, 302], dtype=np.int32),
            x_pc_mm=np.array([1.0, 2.0, 3.0], dtype=np.float64),
            y_pc_mm=np.array([-1.0, -2.0, -3.0], dtype=np.float64),
            time_pc_ns=np.array([5.0, 6.0, 7.0], dtype=np.float64),
            wavelength_nm=np.array([400.0, 500.0, 650.0], dtype=np.float64),
        )

    def _config_payload(self) -> dict[str, object]:
        """Build a minimal valid SimConfig payload with MCP parameters."""

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
                "mcp": {
                    "stage1MeanGain": 10.0,
                    "stage1GainShape": 2.5,
                    "stage2MeanGain": 900.0,
                    "stage2GainShape": 2.0,
                    "gainRef": 1000.0,
                    "spreadSigma0Mm": 0.03,
                    "spreadGainExponent": 0.4,
                },
            },
            "Metadata": {
                "author": "Unit Test",
                "date": "2026-03-19",
                "version": "test",
                "description": "MCP stage test payload.",
                "RunEnvironment": {
                    "SimulationRunID": "mcp_stage_test",
                    "WorkingDirectory": "data",
                    "MacroDirectory": "macros",
                    "LogDirectory": "logs",
                },
            },
        }

    def test_compute_mcp_spread_sigma_mm_scales_with_gain(self) -> None:
        params = self.McpParams(
            stage1_mean_gain=10.0,
            stage1_gain_shape=2.0,
            stage2_mean_gain=100.0,
            stage2_gain_shape=2.0,
            gain_ref=1000.0,
            spread_sigma0_mm=0.03,
            spread_gain_exponent=0.4,
        )

        sigma = self.compute_mcp_spread_sigma_mm(
            np.array([1000.0, 10000.0], dtype=np.float64),
            params,
        )

        np.testing.assert_allclose(
            sigma,
            np.array([0.03, 0.03 * 10.0**0.4], dtype=np.float64),
        )

    def test_convert_photoelectrons_to_mcp_events_preserves_metadata(self) -> None:
        photoelectrons = self._photoelectrons()
        params = self.McpParams(
            stage1_mean_gain=10.0,
            stage1_gain_shape=2.0,
            stage2_mean_gain=100.0,
            stage2_gain_shape=2.0,
            gain_ref=1000.0,
            spread_sigma0_mm=0.0,
            spread_gain_exponent=0.4,
        )

        result = self.convert_photoelectrons_to_mcp_events(
            photoelectrons,
            params,
            rng=np.random.default_rng(123),
        )

        self.assertEqual(len(result), len(photoelectrons))
        np.testing.assert_array_equal(result.source_photon_index, photoelectrons.source_photon_index)
        np.testing.assert_array_equal(result.gun_call_id, photoelectrons.gun_call_id)
        np.testing.assert_array_equal(result.primary_track_id, photoelectrons.primary_track_id)
        np.testing.assert_array_equal(result.secondary_track_id, photoelectrons.secondary_track_id)
        np.testing.assert_array_equal(result.photon_track_id, photoelectrons.photon_track_id)
        np.testing.assert_allclose(result.x_mcp_mm, photoelectrons.x_pc_mm)
        np.testing.assert_allclose(result.y_mcp_mm, photoelectrons.y_pc_mm)
        np.testing.assert_allclose(result.time_mcp_ns, photoelectrons.time_pc_ns)
        np.testing.assert_allclose(result.wavelength_nm, photoelectrons.wavelength_nm)
        np.testing.assert_allclose(result.total_gain, result.stage1_gain * result.stage2_gain)
        self.assertTrue(np.all(result.stage1_gain > 0.0))
        self.assertTrue(np.all(result.stage2_gain > 0.0))

    def test_convert_photoelectrons_to_mcp_events_applies_spatial_spread(self) -> None:
        photoelectrons = self._photoelectrons()
        params = self.McpParams(
            stage1_mean_gain=10.0,
            stage1_gain_shape=2.0,
            stage2_mean_gain=100.0,
            stage2_gain_shape=2.0,
            gain_ref=1000.0,
            spread_sigma0_mm=0.1,
            spread_gain_exponent=0.0,
        )

        result = self.convert_photoelectrons_to_mcp_events(
            photoelectrons,
            params,
            rng=np.random.default_rng(123),
        )

        self.assertFalse(np.allclose(result.x_mcp_mm, photoelectrons.x_pc_mm))
        self.assertFalse(np.allclose(result.y_mcp_mm, photoelectrons.y_pc_mm))

    def test_mcp_params_can_be_built_from_sim_config(self) -> None:
        try:
            from src.config.SimConfig import SimConfig
        except ModuleNotFoundError as exc:
            missing = (getattr(exc, "name", "") or "").lower()
            if missing in {"pydantic"}:
                raise unittest.SkipTest(
                    f"Missing dependency for SimConfig tests: {exc}. "
                    "Run in the project environment (for example: pixi run test-python)."
                ) from exc
            raise

        config = SimConfig.model_validate(self._config_payload())
        params = self.mcp_params_from_sim_config(config)

        self.assertAlmostEqual(params.stage1_mean_gain, 10.0)
        self.assertAlmostEqual(params.stage1_gain_shape, 2.5)
        self.assertAlmostEqual(params.stage2_mean_gain, 900.0)
        self.assertAlmostEqual(params.stage2_gain_shape, 2.0)
        self.assertAlmostEqual(params.gain_ref, 1000.0)
        self.assertAlmostEqual(params.spread_sigma0_mm, 0.03)
        self.assertAlmostEqual(params.spread_gain_exponent, 0.4)


if __name__ == "__main__":
    unittest.main()
