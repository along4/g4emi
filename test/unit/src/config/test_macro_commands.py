"""Unit tests for YAML-to-macro command generation."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import textwrap
import unittest


def _repo_root() -> Path:
    """Resolve repository root by searching parent directories."""

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src").is_dir() and (parent / "pixi.toml").is_file():
            return parent
    raise RuntimeError("Could not resolve repository root from test path.")


# Ensure repository root is importable when this file is run directly.
sys.path.insert(0, str(_repo_root()))


class MacroCommandGenerationTests(unittest.TestCase):
    """Validate deterministic macro command emission from YAML input."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load config IO callables or skip when runtime deps are missing."""

        try:
            from src.config.ConfigIO import (
                from_yaml,
                macro_commands,
                resolve_data_directory,
                write_macro,
            )
        except ModuleNotFoundError as exc:
            missing_name = (getattr(exc, "name", "") or "").lower()
            message = str(exc).lower()
            if "pydantic" in missing_name or "yaml" in missing_name:
                raise unittest.SkipTest(
                    f"Missing dependency for config tests: {exc}. "
                    "Run in the project environment (for example: pixi run test-python)."
                ) from exc
            if "pydantic" in message or "yaml" in message:
                raise unittest.SkipTest(
                    f"Missing dependency for config tests: {exc}. "
                    "Run in the project environment (for example: pixi run test-python)."
                ) from exc
            raise

        cls._from_yaml = staticmethod(from_yaml)
        cls._macro_commands = staticmethod(macro_commands)
        cls._resolve_data_directory = staticmethod(resolve_data_directory)
        cls._write_macro = staticmethod(write_macro)

    @staticmethod
    def _write_yaml_config(destination: Path) -> Path:
        """Write a representative hierarchical YAML config and return its path."""

        yaml_text = textwrap.dedent(
            """
            scintillator:
              position_mm:
                x_mm: 0.0
                y_mm: 0.0
                z_mm: 0.0
              dimension_mm:
                x_mm: 100.0
                y_mm: 100.0
                z_mm: 20.0
              properties:
                name: EJ200
                photonEnergy: [2.8, 3.0, 3.2]
                rIndex: [1.58, 1.59, 1.60]
                nKEntries: 3
                timeConstant: 2.1

            source:
              position_mm:
                x_mm: 0.0
                y_mm: 0.0
                z_mm: -100.0
              dimension_mm:
                x_mm: 10.0
                y_mm: 10.0
                z_mm: 10.0
              energyInfo:
                type: monoenergetic
                value: 6.0
              species: neutron

            optical:
              lenses:
                - name: CanonEF50mmf1.0L
                  primary: true
                  zmxFile: CanonEF50mmf1.0L.zmx
              geometry:
                entranceDiameter: 60.55
                sensorMaxWidth: 36.0
              sensitiveDetectorConfig:
                position_mm:
                  x_mm: 0.0
                  y_mm: 0.0
                  z_mm: 210.05
                shape: circle
                diameterRule: min(entranceDiameter,sensorMaxWidth)

            Metadata:
              author: Unit Test
              date: 2026-02-19
              version: test
              description: Validate macro command generation.
              WorkingDirectory: .
              OutputInfo:
                DataDirectory: data
                LogDirectory: data/logs
                OutputFormat: hdf5
              SimulationRunID: unit_macro_test

            # Script-level extra should be ignored by ConfigIO.from_yaml.
            append_macro_commands:
              - /run/beamOn 10
            """
        ).strip()

        path = destination / "sim_config.yaml"
        path.write_text(yaml_text + "\n", encoding="utf-8")
        return path

    def test_yaml_to_macro_commands(self) -> None:
        """Parse YAML and assert exact macro command list."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            yaml_path = self._write_yaml_config(tmp_path)

            config = self._from_yaml(yaml_path)
            commands = self._macro_commands(config)

            expected = [
                "/output/format hdf5",
                f"/output/path {self._resolve_data_directory(config)}",
                "/output/filename photon_optical_interface_hits",
                "/output/runname unit_macro_test",
                "/scintillator/geom/material EJ200",
                "/scintillator/geom/scintX 100 mm",
                "/scintillator/geom/scintY 100 mm",
                "/scintillator/geom/scintZ 20 mm",
                "/scintillator/geom/posX 0 mm",
                "/scintillator/geom/posY 0 mm",
                "/scintillator/geom/posZ 0 mm",
                "/scintillator/geom/apertureRadius 18 mm",
                "/optical_interface/geom/sizeX 60.55 mm",
                "/optical_interface/geom/sizeY 60.55 mm",
                "/optical_interface/geom/thickness 0.1 mm",
                "/optical_interface/geom/posX 0 mm",
                "/optical_interface/geom/posY 0 mm",
                "/optical_interface/geom/posZ 210.05 mm",
                "/run/initialize",
            ]
            self.assertEqual(commands, expected)

    def test_write_macro_outputs_same_lines(self) -> None:
        """write_macro should persist the same sequence returned by macro_commands."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            yaml_path = self._write_yaml_config(tmp_path)
            macro_path = tmp_path / "generated.mac"

            config = self._from_yaml(yaml_path)
            expected = self._macro_commands(config)

            self._write_macro(
                config,
                macro_path=macro_path,
                include_output=True,
                include_run_initialize=True,
                create_output_directories=False,
                overwrite=True,
            )

            written_lines = macro_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(written_lines, expected)


if __name__ == "__main__":
    unittest.main()
