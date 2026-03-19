"""Unit tests for intensifier input-screen SimConfig schema."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


def _repo_root() -> Path:
    """Resolve repository root by searching parent directories."""

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src").is_dir() and (parent / "pixi.toml").is_file():
            return parent
    raise RuntimeError("Could not resolve repository root from test path.")


sys.path.insert(0, str(_repo_root()))


class SimConfigIntensifierTests(unittest.TestCase):
    """Validate intensifier input-screen center parsing."""

    @classmethod
    def setUpClass(cls) -> None:
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
        cls.SimConfig = SimConfig

    def _base_payload(self) -> dict[str, object]:
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
            "Metadata": {
                "author": "Unit Test",
                "date": "2026-03-05",
                "version": "test",
                "description": "SimConfig intensifier schema test payload.",
                "RunEnvironment": {
                    "SimulationRunID": "simconfig_intensifier_test",
                    "WorkingDirectory": "data",
                    "MacroDirectory": "macros",
                    "LogDirectory": "logs",
                },
            },
        }

    def test_intensifier_center_accepts_sequence(self) -> None:
        payload = self._base_payload()
        payload["intensifier"] = {
            "model": "Cricket2",
            "input_screen": {
                "image_circle_diameter_mm": 18.0,
                "center_mm": [1.25, -2.5],
                "magnification": 1.0,
            },
        }

        config = self.SimConfig.model_validate(payload)
        self.assertEqual(config.intensifier.input_screen.center_mm, (1.25, -2.5))

    def test_intensifier_center_accepts_mapping(self) -> None:
        payload = self._base_payload()
        payload["intensifier"] = {
            "model": "CricketPro",
            "input_screen": {
                "image_circle_diameter_mm": 25.0,
                "center_mm": {"x_mm": 3.0, "y_mm": -1.0},
                "magnification": 1.0,
            },
        }

        config = self.SimConfig.model_validate(payload)
        self.assertEqual(config.intensifier.input_screen.center_mm, (3.0, -1.0))

    def test_intensifier_center_accepts_xy_mapping(self) -> None:
        payload = self._base_payload()
        payload["intensifier"] = {
            "model": "CricketPro",
            "input_screen": {
                "image_circle_diameter_mm": 25.0,
                "center_mm": {"x": 4.5, "y": -2.25},
                "magnification": 1.0,
            },
        }

        config = self.SimConfig.model_validate(payload)
        self.assertEqual(config.intensifier.input_screen.center_mm, (4.5, -2.25))

    def test_rejects_profiles_with_no_active_time_components(self) -> None:
        payload = self._base_payload()
        payload["scintillator"]["properties"]["timeComponents"]["default"] = [
            {"timeConstant": 0.0, "yieldFraction": 1.0},
            {"timeConstant": 0.0, "yieldFraction": 0.0},
            {"timeConstant": 0.0, "yieldFraction": 0.0},
        ]

        with self.assertRaises(ValueError):
            self.SimConfig.model_validate(payload)

    def test_intensifier_stage_parameters_are_parsed(self) -> None:
        payload = self._base_payload()
        payload["intensifier"] = {
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
            "mcp": {
                "stage1MeanGain": 10.0,
                "stage1GainShape": 2.5,
                "stage2MeanGain": 900.0,
                "stage2GainShape": 2.0,
                "gainRef": 1000.0,
                "spreadSigma0Mm": 0.03,
                "spreadGainExponent": 0.4,
            },
            "phosphor": {
                "phosphorGain": 1.2,
                "decayFastNs": 70.0,
                "decaySlowNs": 200.0,
                "fastFraction": 0.85,
                "psfSigmaMm": 0.04,
            },
        }

        config = self.SimConfig.model_validate(payload)
        self.assertEqual(
            config.intensifier.photocathode.qe_wavelength_nm,
            [350.0, 500.0, 650.0],
        )
        self.assertEqual(
            config.intensifier.photocathode.qe_values,
            [0.1, 0.2, 0.05],
        )
        self.assertAlmostEqual(config.intensifier.photocathode.collection_efficiency, 0.8)
        self.assertAlmostEqual(config.intensifier.photocathode.tts_sigma_ns, 0.15)
        self.assertAlmostEqual(config.intensifier.mcp.stage1_mean_gain, 10.0)
        self.assertAlmostEqual(config.intensifier.phosphor.fast_fraction, 0.85)


if __name__ == "__main__":
    unittest.main()
