"""Unit tests for runner-related SimConfig schema."""

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


class SimConfigRunnerTests(unittest.TestCase):
    """Validate runner defaults, aliases, and field constraints."""

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
                "date": "2026-03-10",
                "version": "test",
                "description": "SimConfig runner schema test payload.",
                "RunEnvironment": {
                    "SimulationRunID": "simconfig_runner_test",
                    "WorkingDirectory": "data",
                    "MacroDirectory": "macros",
                    "LogDirectory": "logs",
                },
            },
        }

    def test_runner_defaults_when_block_omitted(self) -> None:
        payload = self._base_payload()

        config = self.SimConfig.model_validate(payload)

        self.assertEqual(config.runner.binary, "g4emi")
        self.assertFalse(config.runner.show_progress)
        self.assertTrue(config.runner.verify_output)
        self.assertTrue(config.optical.show_transport_progress)
        self.assertEqual(config.metadata.run_environment.sub_run_number, 0)

    def test_runner_accepts_verify_output_alias_and_serializes_by_alias(self) -> None:
        payload = self._base_payload()
        payload["runner"] = {
            "binary": "pixi run g4emi",
            "showProgress": False,
            "verifyOutput": False,
        }
        payload["optical"]["showTransportProgress"] = False

        config = self.SimConfig.model_validate(payload)
        dumped = config.model_dump(mode="python", by_alias=True)

        self.assertEqual(config.runner.binary, "pixi run g4emi")
        self.assertFalse(config.runner.show_progress)
        self.assertFalse(config.runner.verify_output)
        self.assertEqual(dumped["runner"]["binary"], "pixi run g4emi")
        self.assertFalse(dumped["runner"]["showProgress"])
        self.assertFalse(dumped["runner"]["verifyOutput"])
        self.assertFalse(dumped["optical"]["showTransportProgress"])
        self.assertNotIn("show_progress", dumped["runner"])
        self.assertNotIn("verify_output", dumped["runner"])

    def test_runner_accepts_field_name_for_verify_output(self) -> None:
        payload = self._base_payload()
        payload["runner"] = {"show_progress": False, "verify_output": False}
        payload["optical"]["show_transport_progress"] = False

        config = self.SimConfig.model_validate(payload)

        self.assertFalse(config.runner.show_progress)
        self.assertFalse(config.runner.verify_output)
        self.assertFalse(config.optical.show_transport_progress)

    def test_runner_rejects_blank_binary(self) -> None:
        payload = self._base_payload()
        payload["runner"] = {"binary": "   "}

        with self.assertRaises(ValueError):
            self.SimConfig.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
