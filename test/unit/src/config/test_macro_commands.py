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
                resolve_run_environment_directory,
                resolve_run_environment_paths,
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
        cls._resolve_run_environment_directory = staticmethod(
            resolve_run_environment_directory
        )
        cls._resolve_run_environment_paths = staticmethod(
            resolve_run_environment_paths
        )
        cls._write_macro = staticmethod(write_macro)

    @staticmethod
    def _write_yaml_config(
        destination: Path,
        *,
        simulation_run_id: str = "unit_macro_test",
        working_directory: str | None = None,
        number_of_particles: int | None = None,
        runtime_controls: dict[str, object] | None = None,
    ) -> Path:
        """Write a representative hierarchical YAML config and return its path."""

        if working_directory is None:
            working_directory = destination.as_posix()

        yaml_sections = [
            textwrap.dedent(
                f"""
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
                    timeComponents:
                      default:
                        - timeConstant: 2.1
                          yieldFraction: 1.0
                        - timeConstant: 0.0
                          yieldFraction: 0.0
                        - timeConstant: 0.0
                          yieldFraction: 0.0

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
                      rot1: {{x: 1.0, y: 0.0, z: 0.0}}
                      rot2: {{x: 0.0, y: 1.0, z: 0.0}}
                      direction: {{x: 0.0, y: 0.0, z: 1.0}}
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
                  RunEnvironment:
                    SimulationRunID: {simulation_run_id}
                    WorkingDirectory: {working_directory}
                    MacroDirectory: macros
                    LogDirectory: logs
                    OutputInfo:
                      SimulatedPhotonsDirectory: simulatedPhotons
                      TransportedPhotonsDirectory: transportedPhotons
                      OutputFormat: hdf5
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
                f"/output/path {self._resolve_run_environment_directory(config, 'data')}",
                "/output/filename photon_optical_interface_hits",
                "/output/runname unit_macro_test",
                "/scintillator/geom/material EJ200",
                "/scintillator/geom/scintX 100 mm",
                "/scintillator/geom/scintY 100 mm",
                "/scintillator/geom/scintZ 20 mm",
                "/scintillator/geom/posX 0 mm",
                "/scintillator/geom/posY 0 mm",
                "/scintillator/geom/posZ 0 mm",
                "/scintillator/properties/photonEnergy 2.8,3,3.2 eV",
                "/scintillator/properties/rIndex 1.58,1.59,1.6",
                "/scintillator/properties/timeConstant1 2.1 ns",
                "/scintillator/properties/yieldFraction1 1",
                "/scintillator/properties/timeConstant2 0 ns",
                "/scintillator/properties/yieldFraction2 0",
                "/scintillator/properties/timeConstant3 0 ns",
                "/scintillator/properties/yieldFraction3 0",
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

            config = self._from_yaml(yaml_path)
            expected = self._macro_commands(config)
            macro_path = self._resolve_run_environment_paths(config).macro_file

            self._write_macro(
                config,
                include_output=True,
                include_run_initialize=True,
                create_output_directories=True,
                overwrite=True,
            )

            written_lines = macro_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(written_lines, expected)

    def test_from_macro_round_trip_with_template(self) -> None:
        """from_macro should reconstruct geometry/output commands with a template."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            yaml_path = self._write_yaml_config(tmp_path)

            config = self._from_yaml(yaml_path)
            expected = self._macro_commands(config)
            macro_path = self._resolve_run_environment_paths(config).macro_file

            self._write_macro(
                config,
                include_output=True,
                include_run_initialize=True,
                create_output_directories=True,
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

    def test_from_yaml_hydrates_scintillator_properties_from_catalog_id(self) -> None:
        """`scintillator.catalogId` should backfill missing properties from catalog."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            yaml_path = tmp_path / "catalog_only_scintillator.yaml"
            yaml_path.write_text(
                textwrap.dedent(
                    """
                    scintillator:
                      catalogId: EJ200
                      position_mm:
                        x_mm: 0.0
                        y_mm: 0.0
                        z_mm: 0.0
                      dimension_mm:
                        x_mm: 100.0
                        y_mm: 100.0
                        z_mm: 20.0

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
                      description: Validate catalogId hydration.
                      RunEnvironment:
                        SimulationRunID: unit_catalog_hydration
                        WorkingDirectory: data
                        MacroDirectory: macros
                        LogDirectory: logs
                        OutputInfo:
                          SimulatedPhotonsDirectory: simulatedPhotons
                          TransportedPhotonsDirectory: transportedPhotons
                          OutputFormat: hdf5
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            config = self._from_yaml(yaml_path)
            self.assertEqual(config.scintillator.catalog_id, "EJ200")
            self.assertIsNotNone(config.scintillator.properties)
            assert config.scintillator.properties is not None
            self.assertEqual(config.scintillator.properties.name, "EJ200")
            self.assertEqual(config.scintillator.properties.n_k_entries, 5)
            self.assertEqual(len(config.scintillator.properties.photon_energy), 5)
            self.assertIsNotNone(config.scintillator.properties.abs_length)
            self.assertIsNotNone(config.scintillator.properties.scint_spectrum)
            default_profile = config.scintillator.properties.time_components.default
            assert default_profile is not None
            self.assertAlmostEqual(
                default_profile[0].time_constant,
                2.1,
            )
            self.assertEqual(
                [
                    component.time_constant
                    for component in default_profile
                ],
                [2.1, 0.0, 0.0],
            )
            self.assertEqual(
                [
                    component.yield_fraction
                    for component in default_profile
                ],
                [1.0, 0.0, 0.0],
            )

            commands = self._macro_commands(config)
            self.assertIn("/scintillator/geom/material EJ200", commands)
            self.assertIn("/scintillator/properties/density 1.023 g/cm3", commands)
            self.assertIn("/scintillator/properties/carbonAtoms 9", commands)
            self.assertIn("/scintillator/properties/hydrogenAtoms 10", commands)
            self.assertIn(
                "/scintillator/properties/photonEnergy 2,2.4,2.76,3.1,3.5 eV",
                commands,
            )
            self.assertIn("/scintillator/properties/scintYield 10000", commands)

    def test_from_macro_parses_scintillator_property_commands(self) -> None:
        """Scintillator property commands should populate extended properties."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            macro_path = tmp_path / "scintillator_properties.mac"
            macro_path.write_text(
                "\n".join(
                    [
                        "/output/format hdf5",
                        "/output/path data",
                        "/output/runname prop_import",
                        "/scintillator/geom/material EJ200",
                        "/scintillator/geom/scintX 100 mm",
                        "/scintillator/geom/scintY 100 mm",
                        "/scintillator/geom/scintZ 20 mm",
                        "/scintillator/geom/posX 0 mm",
                        "/scintillator/geom/posY 0 mm",
                        "/scintillator/geom/posZ 0 mm",
                        "/scintillator/properties/density 1.023 g/cm3",
                        "/scintillator/properties/carbonAtoms 9",
                        "/scintillator/properties/hydrogenAtoms 10",
                        "/scintillator/properties/photonEnergy 2.0,2.4,2.76,3.1,3.5 eV",
                        "/scintillator/properties/rIndex 1.58,1.58,1.58,1.58,1.58",
                        "/scintillator/properties/absLength 380,380,380,300,220 cm",
                        "/scintillator/properties/scintSpectrum 0.05,0.35,1.0,0.45,0.08",
                        "/scintillator/properties/scintYield 10000",
                        "/scintillator/properties/resolutionScale 1.0",
                        "/scintillator/properties/timeConstant1 2.1 ns",
                        "/scintillator/properties/yieldFraction1 1.0",
                        "/scintillator/properties/timeConstant2 0 ns",
                        "/scintillator/properties/yieldFraction2 0.0",
                        "/scintillator/properties/timeConstant3 0 ns",
                        "/scintillator/properties/yieldFraction3 0.0",
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
            props = imported.scintillator.properties
            assert props is not None
            self.assertAlmostEqual(props.density or 0.0, 1.023)
            self.assertEqual(props.carbon_atoms, 9)
            self.assertEqual(props.hydrogen_atoms, 10)
            self.assertEqual(props.n_k_entries, 5)
            self.assertIsNotNone(props.abs_length)
            self.assertIsNotNone(props.scint_spectrum)
            self.assertAlmostEqual(props.scint_yield or 0.0, 10000.0)
            self.assertAlmostEqual(props.resolution_scale or 0.0, 1.0)
            profile_name, components = props.time_components.resolve_for_particle(
                imported.source.gps.particle
            )
            self.assertEqual(profile_name, "neutron")
            self.assertAlmostEqual(components[0].yield_fraction, 1.0)
            self.assertAlmostEqual(components[1].yield_fraction, 0.0)
            self.assertAlmostEqual(components[2].yield_fraction, 0.0)

    def test_from_macro_rejects_legacy_time_component_commands(self) -> None:
        """Legacy single-component time commands should be rejected."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            macro_path = tmp_path / "legacy_time_commands.mac"
            macro_path.write_text(
                "\n".join(
                    [
                        "/scintillator/properties/timeConstant 2.1 ns",
                        "/scintillator/properties/yield1 1.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                self._from_macro(macro_path)

    def test_time_components_select_neutron_profile_for_neutron_source(self) -> None:
        """Neutron source should emit neutron profile time constants."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            yaml_path = tmp_path / "neutron_profile.yaml"
            yaml_path.write_text(
                textwrap.dedent(
                    """
                    scintillator:
                      position_mm: {x_mm: 0.0, y_mm: 0.0, z_mm: 0.0}
                      dimension_mm: {x_mm: 100.0, y_mm: 100.0, z_mm: 20.0}
                      properties:
                        name: EJ-276D
                        photonEnergy: [2.8, 3.0, 3.2]
                        rIndex: [1.58, 1.59, 1.60]
                        nKEntries: 3
                        timeComponents:
                          default:
                            - timeConstant: 2.1
                              yieldFraction: 1.0
                            - timeConstant: 0.0
                              yieldFraction: 0.0
                            - timeConstant: 0.0
                              yieldFraction: 0.0
                          neutron:
                            - timeConstant: 13.0
                              yieldFraction: 1.0
                            - timeConstant: 59.0
                              yieldFraction: 0.0
                            - timeConstant: 460.0
                              yieldFraction: 0.0
                          gamma:
                            - timeConstant: 13.0
                              yieldFraction: 1.0
                            - timeConstant: 35.0
                              yieldFraction: 0.0
                            - timeConstant: 270.0
                              yieldFraction: 0.0
                    source:
                      gps:
                        particle: neutron
                        position:
                          type: Plane
                          shape: Circle
                          centerMm: {x_mm: 0.0, y_mm: 0.0, z_mm: -100.0}
                          radiusMm: 10.0
                        angular:
                          type: beam2d
                          rot1: {x: 1.0, y: 0.0, z: 0.0}
                          rot2: {x: 0.0, y: 1.0, z: 0.0}
                          direction: {x: 0.0, y: 0.0, z: 1.0}
                        energy: {type: Mono, monoMeV: 6.0}
                    optical:
                      lenses:
                        - name: CanonEF50mmf1.0L
                          primary: true
                          zmxFile: CanonEF50mmf1.0L.zmx
                      geometry: {entranceDiameter: 60.55, sensorMaxWidth: 36.0}
                      sensitiveDetectorConfig:
                        position_mm: {x_mm: 0.0, y_mm: 0.0, z_mm: 210.05}
                        shape: circle
                        diameterRule: min(entranceDiameter,sensorMaxWidth)
                    Metadata:
                      author: Unit Test
                      date: 2026-02-26
                      version: test
                      description: Profile selection
                      RunEnvironment:
                        SimulationRunID: neutron_profile
                        WorkingDirectory: data
                        MacroDirectory: macros
                        LogDirectory: logs
                        OutputInfo:
                          SimulatedPhotonsDirectory: simulatedPhotons
                          TransportedPhotonsDirectory: transportedPhotons
                          OutputFormat: hdf5
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            config = self._from_yaml(yaml_path)
            commands = self._macro_commands(config)
            self.assertIn("/scintillator/properties/timeConstant2 59 ns", commands)
            self.assertIn("/scintillator/properties/timeConstant3 460 ns", commands)

    def test_time_components_select_gamma_profile_for_gamma_source(self) -> None:
        """Gamma source should emit gamma profile time constants."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            yaml_path = tmp_path / "gamma_profile.yaml"
            yaml_path.write_text(
                textwrap.dedent(
                    """
                    scintillator:
                      position_mm: {x_mm: 0.0, y_mm: 0.0, z_mm: 0.0}
                      dimension_mm: {x_mm: 100.0, y_mm: 100.0, z_mm: 20.0}
                      properties:
                        name: EJ-276G
                        photonEnergy: [2.8, 3.0, 3.2]
                        rIndex: [1.58, 1.59, 1.60]
                        nKEntries: 3
                        timeComponents:
                          default:
                            - timeConstant: 2.1
                              yieldFraction: 1.0
                            - timeConstant: 0.0
                              yieldFraction: 0.0
                            - timeConstant: 0.0
                              yieldFraction: 0.0
                          gamma:
                            - timeConstant: 13.0
                              yieldFraction: 1.0
                            - timeConstant: 35.0
                              yieldFraction: 0.0
                            - timeConstant: 270.0
                              yieldFraction: 0.0
                    source:
                      gps:
                        particle: gamma
                        position:
                          type: Plane
                          shape: Circle
                          centerMm: {x_mm: 0.0, y_mm: 0.0, z_mm: -100.0}
                          radiusMm: 10.0
                        angular:
                          type: beam2d
                          rot1: {x: 1.0, y: 0.0, z: 0.0}
                          rot2: {x: 0.0, y: 1.0, z: 0.0}
                          direction: {x: 0.0, y: 0.0, z: 1.0}
                        energy: {type: Mono, monoMeV: 6.0}
                    optical:
                      lenses:
                        - name: CanonEF50mmf1.0L
                          primary: true
                          zmxFile: CanonEF50mmf1.0L.zmx
                      geometry: {entranceDiameter: 60.55, sensorMaxWidth: 36.0}
                      sensitiveDetectorConfig:
                        position_mm: {x_mm: 0.0, y_mm: 0.0, z_mm: 210.05}
                        shape: circle
                        diameterRule: min(entranceDiameter,sensorMaxWidth)
                    Metadata:
                      author: Unit Test
                      date: 2026-02-26
                      version: test
                      description: Profile selection
                      RunEnvironment:
                        SimulationRunID: gamma_profile
                        WorkingDirectory: data
                        MacroDirectory: macros
                        LogDirectory: logs
                        OutputInfo:
                          SimulatedPhotonsDirectory: simulatedPhotons
                          TransportedPhotonsDirectory: transportedPhotons
                          OutputFormat: hdf5
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            config = self._from_yaml(yaml_path)
            commands = self._macro_commands(config)
            self.assertIn("/scintillator/properties/timeConstant2 35 ns", commands)
            self.assertIn("/scintillator/properties/timeConstant3 270 ns", commands)


if __name__ == "__main__":
    unittest.main()
