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
                from_macro,
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

        cls._from_macro = staticmethod(from_macro)
        cls._from_yaml = staticmethod(from_yaml)
        cls._macro_commands = staticmethod(macro_commands)
        cls._resolve_data_directory = staticmethod(resolve_data_directory)
        cls._write_macro = staticmethod(write_macro)

    @staticmethod
    def _write_yaml_config(
        destination: Path,
        *,
        number_of_particles: int | None = None,
        runtime_controls: dict[str, object] | None = None,
    ) -> Path:
        """Write a representative hierarchical YAML config and return its path."""

        yaml_sections = [
            textwrap.dedent(
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
                  gps:
                    particle: neutron
                    position:
                      type: Plane
                      shape: Circle
                      centerMm:
                        x_mm: 0.0
                        y_mm: 0.0
                        z_mm: -100.0
                      radiusMm: 10.0
                    angular:
                      type: beam2d
                      rot1: {x: 1.0, y: 0.0, z: 0.0}
                      rot2: {x: 0.0, y: 1.0, z: 0.0}
                      direction: {x: 0.0, y: 0.0, z: 1.0}
                    energy:
                      type: Mono
                      monoMeV: 6.0

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
                """
            ).strip()
        ]

        if number_of_particles is not None or runtime_controls is not None:
            simulation_lines = ["simulation:"]
            if number_of_particles is not None:
                simulation_lines.append(f"  numberOfParticles: {number_of_particles}")
            if runtime_controls is not None:
                simulation_lines.append("  runtimeControls:")
                for key, value in runtime_controls.items():
                    yaml_value = str(value).lower() if isinstance(value, bool) else value
                    simulation_lines.append(f"    {key}: {yaml_value}")
            yaml_sections.append("\n".join(simulation_lines))

        yaml_sections.append(
            textwrap.dedent(
                """
                # Script-level extra should be ignored by ConfigIO.from_yaml.
                macro_output_path: ./tmp/generated.mac
                """
            ).strip()
        )

        yaml_text = "\n\n".join(yaml_sections)

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
                "/gps/particle neutron",
                "/gps/pos/type Plane",
                "/gps/pos/shape Circle",
                "/gps/pos/centre 0 0 -100 mm",
                "/gps/pos/radius 10 mm",
                "/gps/ang/type beam2d",
                "/gps/ang/rot1 1 0 0",
                "/gps/ang/rot2 0 1 0",
                "/gps/direction 0 0 1",
                "/gps/ene/type Mono",
                "/gps/ene/mono 6 MeV",
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

    def test_from_macro_round_trip_with_template(self) -> None:
        """from_macro should reconstruct geometry/output commands with a template."""

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

            imported = self._from_macro(macro_path, template=config)
            reconstructed = self._macro_commands(imported)
            self.assertEqual(reconstructed, expected)

    def test_from_macro_without_aperture_disables_aperture_command(self) -> None:
        """Missing aperture command should map to non-circular detector shape."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            macro_path = tmp_path / "no_aperture.mac"
            macro_path.write_text(
                "\n".join(
                    [
                        "/output/format hdf5",
                        "/output/path data",
                        "/output/runname no_aperture_case",
                        "/scintillator/geom/material EJ200",
                        "/scintillator/geom/scintX 100 mm",
                        "/scintillator/geom/scintY 100 mm",
                        "/scintillator/geom/scintZ 20 mm",
                        "/scintillator/geom/posX 0 mm",
                        "/scintillator/geom/posY 0 mm",
                        "/scintillator/geom/posZ 0 mm",
                        "/optical_interface/geom/sizeX 60.55 mm",
                        "/optical_interface/geom/sizeY 60.55 mm",
                        "/optical_interface/geom/thickness 0.1 mm",
                        "/optical_interface/geom/posX 0 mm",
                        "/optical_interface/geom/posY 0 mm",
                        "/optical_interface/geom/posZ 210.05 mm",
                        "/run/initialize",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            imported = self._from_macro(macro_path)
            commands = self._macro_commands(imported)

            self.assertNotIn(
                "/scintillator/geom/apertureRadius 18 mm",
                commands,
            )
            self.assertFalse(
                any(
                    line.startswith("/scintillator/geom/apertureRadius")
                    for line in commands
                )
            )
            self.assertFalse(
                any(line.startswith("/run/beamOn") for line in commands)
            )

    def test_simulation_number_of_particles_maps_to_beam_on(self) -> None:
        """`simulation.numberOfParticles` should emit `/run/beamOn` command."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            yaml_path = self._write_yaml_config(
                tmp_path, number_of_particles=10000
            )

            config = self._from_yaml(yaml_path)
            commands = self._macro_commands(config)

            self.assertIn("/run/beamOn 10000", commands)
            self.assertEqual(commands[-1], "/run/beamOn 10000")

    def test_runtime_controls_emit_macro_preamble_lines(self) -> None:
        """`simulation.runtimeControls` should emit control/run preamble lines."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            yaml_path = self._write_yaml_config(
                tmp_path,
                runtime_controls={
                    "controlVerbose": 0,
                    "runVerbose": 0,
                    "eventVerbose": 0,
                    "trackingVerbose": 0,
                    "printProgress": 1000,
                    "storeTrajectory": True,
                },
            )

            config = self._from_yaml(yaml_path)
            commands = self._macro_commands(config)

            expected_prefix = [
                "/control/verbose 0",
                "/run/verbose 0",
                "/event/verbose 0",
                "/tracking/verbose 0",
                "/run/printProgress 1000",
                "/tracking/storeTrajectory 1",
            ]
            self.assertEqual(commands[: len(expected_prefix)], expected_prefix)

    def test_from_macro_parses_runtime_controls(self) -> None:
        """Runtime preamble commands in macro should populate runtimeControls."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            macro_path = tmp_path / "runtime_controls.mac"
            macro_path.write_text(
                "\n".join(
                    [
                        "/control/verbose 1",
                        "/run/verbose 2",
                        "/event/verbose 3",
                        "/tracking/verbose 4",
                        "/run/printProgress 50",
                        "/tracking/storeTrajectory 1",
                        "/output/format hdf5",
                        "/output/path data",
                        "/output/runname runtime_import",
                        "/scintillator/geom/material EJ200",
                        "/scintillator/geom/scintX 100 mm",
                        "/scintillator/geom/scintY 100 mm",
                        "/scintillator/geom/scintZ 20 mm",
                        "/scintillator/geom/posX 0 mm",
                        "/scintillator/geom/posY 0 mm",
                        "/scintillator/geom/posZ 0 mm",
                        "/optical_interface/geom/sizeX 60.55 mm",
                        "/optical_interface/geom/sizeY 60.55 mm",
                        "/optical_interface/geom/thickness 0.1 mm",
                        "/optical_interface/geom/posX 0 mm",
                        "/optical_interface/geom/posY 0 mm",
                        "/optical_interface/geom/posZ 210.05 mm",
                        "/run/initialize",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            imported = self._from_macro(macro_path)
            self.assertIsNotNone(imported.simulation)
            self.assertIsNotNone(imported.simulation.runtime_controls)
            runtime = imported.simulation.runtime_controls
            assert runtime is not None
            self.assertEqual(runtime.control_verbose, 1)
            self.assertEqual(runtime.run_verbose, 2)
            self.assertEqual(runtime.event_verbose, 3)
            self.assertEqual(runtime.tracking_verbose, 4)
            self.assertEqual(runtime.print_progress, 50)
            self.assertTrue(runtime.store_trajectory)


if __name__ == "__main__":
    unittest.main()
