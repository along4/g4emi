"""Unit tests for the intensifier phosphor stage."""

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


class PhosphorStageTests(unittest.TestCase):
    """Validate phosphor timing, spatial blur, and config integration."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from src.intensifier.models import McpEventBatch
            from src.intensifier.models import PhosphorParams
            from src.intensifier.phosphor import convert_mcp_events_to_intensifier_output
            from src.intensifier.phosphor import phosphor_params_from_sim_config
            from src.intensifier.phosphor import sample_phosphor_delay_ns
        except ModuleNotFoundError as exc:
            missing = (getattr(exc, "name", "") or "").lower()
            if missing in {"numpy"}:
                raise unittest.SkipTest(
                    f"Missing dependency for intensifier tests: {exc}. "
                    "Run in the project environment (for example: pixi run test-python)."
                ) from exc
            raise

        cls.McpEventBatch = McpEventBatch
        cls.PhosphorParams = PhosphorParams
        cls.convert_mcp_events_to_intensifier_output = staticmethod(
            convert_mcp_events_to_intensifier_output
        )
        cls.phosphor_params_from_sim_config = staticmethod(
            phosphor_params_from_sim_config
        )
        cls.sample_phosphor_delay_ns = staticmethod(sample_phosphor_delay_ns)

    def _mcp_events(self) -> object:
        """Build a small deterministic MCP event batch."""

        return self.McpEventBatch(
            source_photon_index=np.array([0, 1, 2], dtype=np.int64),
            gun_call_id=np.array([10, 10, 11], dtype=np.int64),
            primary_track_id=np.array([100, 100, 101], dtype=np.int32),
            secondary_track_id=np.array([200, 201, 202], dtype=np.int32),
            photon_track_id=np.array([300, 301, 302], dtype=np.int32),
            x_mcp_mm=np.array([1.0, 2.0, 3.0], dtype=np.float64),
            y_mcp_mm=np.array([-1.0, -2.0, -3.0], dtype=np.float64),
            time_mcp_ns=np.array([5.0, 6.0, 7.0], dtype=np.float64),
            stage1_gain=np.array([10.0, 11.0, 12.0], dtype=np.float64),
            stage2_gain=np.array([100.0, 110.0, 120.0], dtype=np.float64),
            total_gain=np.array([1000.0, 1210.0, 1440.0], dtype=np.float64),
            wavelength_nm=np.array([400.0, 500.0, 650.0], dtype=np.float64),
        )

    def _config_payload(self) -> dict[str, object]:
        """Build a minimal valid SimConfig payload with phosphor parameters."""

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
                "phosphor": {
                    "phosphorGain": 1.2,
                    "decayFastNs": 70.0,
                    "decaySlowNs": 200.0,
                    "fastFraction": 0.85,
                    "psfSigmaMm": 0.04,
                },
            },
            "Metadata": {
                "author": "Unit Test",
                "date": "2026-03-19",
                "version": "test",
                "description": "Phosphor stage test payload.",
                "RunEnvironment": {
                    "SimulationRunID": "phosphor_stage_test",
                    "WorkingDirectory": "data",
                    "MacroDirectory": "macros",
                    "LogDirectory": "logs",
                },
            },
        }

    def test_sample_phosphor_delay_ns_is_non_negative(self) -> None:
        params = self.PhosphorParams(
            phosphor_gain=1.0,
            decay_fast_ns=70.0,
            decay_slow_ns=200.0,
            fast_fraction=0.85,
            psf_sigma_mm=0.04,
        )

        delays = self.sample_phosphor_delay_ns(
            8,
            params,
            np.random.default_rng(123),
        )

        self.assertEqual(delays.shape, (8,))
        self.assertTrue(np.all(delays >= 0.0))

    def test_convert_mcp_events_to_intensifier_output_preserves_metadata(self) -> None:
        mcp_events = self._mcp_events()
        params = self.PhosphorParams(
            phosphor_gain=1.2,
            decay_fast_ns=70.0,
            decay_slow_ns=200.0,
            fast_fraction=0.85,
            psf_sigma_mm=0.0,
        )

        result = self.convert_mcp_events_to_intensifier_output(
            mcp_events,
            params,
            rng=np.random.default_rng(123),
        )

        self.assertEqual(len(result), len(mcp_events))
        np.testing.assert_array_equal(result.source_photon_index, mcp_events.source_photon_index)
        np.testing.assert_array_equal(result.gun_call_id, mcp_events.gun_call_id)
        np.testing.assert_array_equal(result.primary_track_id, mcp_events.primary_track_id)
        np.testing.assert_array_equal(result.secondary_track_id, mcp_events.secondary_track_id)
        np.testing.assert_array_equal(result.photon_track_id, mcp_events.photon_track_id)
        np.testing.assert_allclose(result.output_x_mm, mcp_events.x_mcp_mm)
        np.testing.assert_allclose(result.output_y_mm, mcp_events.y_mcp_mm)
        np.testing.assert_array_equal(result.total_gain, mcp_events.total_gain)
        np.testing.assert_array_equal(result.wavelength_nm, mcp_events.wavelength_nm)
        np.testing.assert_allclose(
            result.signal_amplitude_arb,
            1.2 * mcp_events.total_gain,
        )
        self.assertTrue(np.all(result.output_time_ns >= mcp_events.time_mcp_ns))

    def test_convert_mcp_events_to_intensifier_output_applies_spatial_blur(self) -> None:
        mcp_events = self._mcp_events()
        params = self.PhosphorParams(
            phosphor_gain=1.0,
            decay_fast_ns=70.0,
            decay_slow_ns=200.0,
            fast_fraction=0.85,
            psf_sigma_mm=0.1,
        )

        result = self.convert_mcp_events_to_intensifier_output(
            mcp_events,
            params,
            rng=np.random.default_rng(123),
        )

        self.assertFalse(np.allclose(result.output_x_mm, mcp_events.x_mcp_mm))
        self.assertFalse(np.allclose(result.output_y_mm, mcp_events.y_mcp_mm))

    def test_phosphor_params_can_be_built_from_sim_config(self) -> None:
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
        params = self.phosphor_params_from_sim_config(config)

        self.assertAlmostEqual(params.phosphor_gain, 1.2)
        self.assertAlmostEqual(params.decay_fast_ns, 70.0)
        self.assertAlmostEqual(params.decay_slow_ns, 200.0)
        self.assertAlmostEqual(params.fast_fraction, 0.85)
        self.assertAlmostEqual(params.psf_sigma_mm, 0.04)


if __name__ == "__main__":
    unittest.main()
