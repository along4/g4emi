"""Unit tests for Timepix sensor models and config integration."""

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


class TimepixModelTests(unittest.TestCase):
    """Validate Timepix params, hit batches, and SimConfig integration."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from src.config.SimConfig import SimConfig
            from src.sensor.models import TimepixHitBatch
            from src.sensor.models import TimepixParams
            from src.sensor.timepix import timepix_params_from_sim_config
        except ModuleNotFoundError as exc:
            missing = (getattr(exc, "name", "") or "").lower()
            if missing in {"numpy", "pydantic"}:
                raise unittest.SkipTest(
                    f"Missing dependency for sensor tests: {exc}. "
                    "Run in the project environment (for example: pixi run test-python)."
                ) from exc
            raise

        cls.SimConfig = SimConfig
        cls.TimepixHitBatch = TimepixHitBatch
        cls.TimepixParams = TimepixParams
        cls.timepix_params_from_sim_config = staticmethod(timepix_params_from_sim_config)

    def _config_payload(self) -> dict[str, object]:
        """Build a minimal valid SimConfig payload with sensor parameters."""

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
                "description": "Timepix model test payload.",
                "RunEnvironment": {
                    "SimulationRunID": "timepix_model_test",
                    "WorkingDirectory": "data",
                    "MacroDirectory": "macros",
                    "LogDirectory": "logs",
                },
            },
        }

    def test_timepix_params_reject_negative_dead_time(self) -> None:
        with self.assertRaises(ValueError):
            self.TimepixParams(
                pixels_x=256,
                pixels_y=256,
                pixel_pitch_mm=0.055,
                max_tot_ns=25550.0,
                dead_time_ns=-1.0,
            )

    def test_timepix_hit_batch_preserves_values(self) -> None:
        batch = self.TimepixHitBatch(
            gun_call_id=np.array([10, 11], dtype=np.int64),
            primary_track_id=np.array([100, 101], dtype=np.int32),
            secondary_track_id=np.array([200, 201], dtype=np.int32),
            x_pixel=np.array([12, 13], dtype=np.int32),
            y_pixel=np.array([14, 15], dtype=np.int32),
            time_of_arrival_ns=np.array([0.0, 0.0], dtype=np.float64),
            time_over_threshold_ns=np.array([25.0, 50.0], dtype=np.float64),
            contribution_count=np.array([1, 3], dtype=np.int32),
        )

        self.assertEqual(len(batch), 2)
        np.testing.assert_array_equal(batch.x_pixel, np.array([12, 13], dtype=np.int32))
        np.testing.assert_array_equal(batch.contribution_count, np.array([1, 3], dtype=np.int32))

    def test_timepix_hit_batch_rejects_mismatched_lengths(self) -> None:
        with self.assertRaises(ValueError):
            self.TimepixHitBatch(
                gun_call_id=np.array([10], dtype=np.int64),
                primary_track_id=np.array([100], dtype=np.int32),
                secondary_track_id=np.array([200], dtype=np.int32),
                x_pixel=np.array([12, 13], dtype=np.int32),
                y_pixel=np.array([14], dtype=np.int32),
                time_of_arrival_ns=np.array([0.0], dtype=np.float64),
                time_over_threshold_ns=np.array([25.0], dtype=np.float64),
                contribution_count=np.array([1], dtype=np.int32),
            )

    def test_timepix_hit_batch_empty_has_expected_dtypes(self) -> None:
        batch = self.TimepixHitBatch.empty()

        self.assertEqual(len(batch), 0)
        self.assertEqual(batch.gun_call_id.dtype, np.int64)
        self.assertEqual(batch.x_pixel.dtype, np.int32)
        self.assertEqual(batch.time_over_threshold_ns.dtype, np.float64)

    def test_timepix_params_from_sim_config_uses_sensor_block(self) -> None:
        config = self.SimConfig.model_validate(self._config_payload())

        params = self.timepix_params_from_sim_config(config)

        self.assertEqual(params.pixels_x, 256)
        self.assertEqual(params.pixels_y, 256)
        self.assertAlmostEqual(params.pixel_pitch_mm, 0.055)
        self.assertAlmostEqual(params.max_tot_ns, 25550.0)
        self.assertAlmostEqual(params.dead_time_ns, 475.0)

    def test_timepix_params_from_sim_config_requires_sensor(self) -> None:
        payload = self._config_payload()
        payload.pop("sensor")
        config = self.SimConfig.model_validate(payload)

        with self.assertRaises(ValueError):
            self.timepix_params_from_sim_config(config)


if __name__ == "__main__":
    unittest.main()
