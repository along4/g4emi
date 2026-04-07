"""Unit tests for SimConfig-driven optical transport HDF5 generation."""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


def _repo_root() -> Path:
    """Resolve repository root by searching parent directories."""

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src").is_dir() and (parent / "pixi.toml").is_file():
            return parent
    raise RuntimeError("Could not resolve repository root from test path.")


sys.path.insert(0, str(_repo_root()))


class _StubTracer:
    """Deterministic tracer used to test transport writer behavior."""

    engine_name = "stub-tracer"

    def trace_to_sensor(
        self,
        *,
        x_mm: float,
        y_mm: float,
        dir_x: float,
        dir_y: float,
        dir_z: float,
        wavelength_nm: float | None,
    ) -> tuple[float, float, float] | None:
        if x_mm >= 0.0:
            return (x_mm + 10.0, y_mm - 5.0, 42.0)
        return None


class OpticalTransportTests(unittest.TestCase):
    """Validate transport output schema and SimConfig integration."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import h5py
            import numpy as np

            from src.config.SimConfig import SimConfig
            from src.common.logger import configure_run_logger
            from src.optics.OpticalTransport import (
                resolve_transport_paths,
                transport_from_sim_config,
            )
        except ModuleNotFoundError as exc:
            missing = (getattr(exc, "name", "") or "").lower()
            if missing in {"h5py", "numpy", "pydantic"}:
                raise unittest.SkipTest(
                    f"Missing dependency for optical-transport tests: {exc}. "
                    "Run in the project environment (for example: pixi run test-python)."
                ) from exc
            raise

        cls.h5py = h5py
        cls.np = np
        cls.SimConfig = SimConfig
        cls.configure_run_logger = staticmethod(configure_run_logger)
        cls.resolve_transport_paths = staticmethod(resolve_transport_paths)
        cls.transport_from_sim_config = staticmethod(transport_from_sim_config)

    def _build_config(
        self,
        working_directory: Path,
        *,
        sub_run_number: int = 0,
        transport_chunk_rows: int | str | None = None,
        transport_chunk_target_mib: float | None = None,
        include_intensifier_screen: bool = True,
        image_circle_diameter_mm: float = 18.0,
        center_mm: tuple[float, float] = (0.0, 0.0),
    ) -> object:
        """Construct a minimal valid SimConfig payload for transport tests."""

        output_info: dict[str, object] = {
            "SimulatedPhotonsDirectory": "simulatedPhotons",
            "TransportedPhotonsDirectory": "transportedPhotons",
        }
        if transport_chunk_rows is not None:
            output_info["TransportChunkRows"] = transport_chunk_rows
        if transport_chunk_target_mib is not None:
            output_info["TransportChunkTargetMiB"] = transport_chunk_target_mib

        payload: dict[str, object] = {
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
                "date": "2026-02-27",
                "version": "test",
                "description": "Optical transport test payload.",
                "RunEnvironment": {
                    "SimulationRunID": "transport_unit_test",
                    "SubRunNumber": sub_run_number,
                    "WorkingDirectory": str(working_directory),
                    "MacroDirectory": "macros",
                    "LogDirectory": "logs",
                    "OutputInfo": output_info,
                },
            },
        }
        if include_intensifier_screen:
            payload["intensifier"] = {
                "model": "Cricket2",
                "input_screen": {
                    "image_circle_diameter_mm": image_circle_diameter_mm,
                    "center_mm": [float(center_mm[0]), float(center_mm[1])],
                    "magnification": 1.0,
                    "coordinate_frame": "intensifier_input_plane",
                },
            }

        return self.SimConfig.model_validate(payload)

    def _write_input_hdf5(self, path: Path) -> None:
        """Write small deterministic input datasets for transport tests."""

        path.parent.mkdir(parents=True, exist_ok=True)
        primaries_dtype = self.np.dtype(
            [
                ("gun_call_id", self.np.int64),
                ("primary_track_id", self.np.int32),
                ("primary_species", "S16"),
                ("primary_x_mm", self.np.float64),
                ("primary_y_mm", self.np.float64),
                ("primary_energy_MeV", self.np.float64),
            ]
        )
        secondaries_dtype = self.np.dtype(
            [
                ("gun_call_id", self.np.int64),
                ("primary_track_id", self.np.int32),
                ("secondary_track_id", self.np.int32),
                ("secondary_species", "S16"),
                ("secondary_origin_x_mm", self.np.float64),
                ("secondary_origin_y_mm", self.np.float64),
                ("secondary_origin_z_mm", self.np.float64),
                ("secondary_origin_energy_MeV", self.np.float64),
                ("secondary_end_x_mm", self.np.float64),
                ("secondary_end_y_mm", self.np.float64),
                ("secondary_end_z_mm", self.np.float64),
            ]
        )
        photons_dtype = self.np.dtype(
            [
                ("gun_call_id", self.np.int64),
                ("primary_track_id", self.np.int32),
                ("secondary_track_id", self.np.int32),
                ("photon_track_id", self.np.int32),
                ("optical_interface_hit_x_mm", self.np.float64),
                ("optical_interface_hit_y_mm", self.np.float64),
                ("optical_interface_hit_time_ns", self.np.float64),
                ("optical_interface_hit_dir_x", self.np.float64),
                ("optical_interface_hit_dir_y", self.np.float64),
                ("optical_interface_hit_dir_z", self.np.float64),
                ("optical_interface_hit_energy_eV", self.np.float64),
                ("optical_interface_hit_wavelength_nm", self.np.float64),
            ]
        )

        primaries = self.np.array(
            [(0, 1, b"n", 0.0, 0.0, 2.45)],
            dtype=primaries_dtype,
        )
        secondaries = self.np.array(
            [(0, 1, 10, b"proton", 0.1, 0.2, 0.3, 1.0, 0.7, 0.8, 0.9)],
            dtype=secondaries_dtype,
        )
        photons = self.np.array(
            [
                (0, 1, 10, 100, 1.5, 2.0, 11.0, 0.0, 0.0, 1.0, 2.1, 500.0),
                (0, 1, 10, 101, -4.0, 1.0, 12.0, 0.0, 0.0, 1.0, 2.1, 500.0),
            ],
            dtype=photons_dtype,
        )

        with self.h5py.File(path, "w") as handle:
            handle.create_dataset("primaries", data=primaries)
            handle.create_dataset("secondaries", data=secondaries)
            handle.create_dataset("photons", data=photons)

    def test_resolve_transport_paths_uses_simconfig_layout(self) -> None:
        """Default path resolution should use run-root stage directories."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._build_config(Path(tmp_dir))
            resolved = self.resolve_transport_paths(config)

            self.assertTrue(str(resolved.input_hdf5).endswith("photon_optical_interface_hits_0000.h5"))
            self.assertTrue(str(resolved.output_hdf5).endswith("photons_intensifier_hits_0000.h5"))
            self.assertIn("simulatedPhotons", str(resolved.input_hdf5))
            self.assertIn("transportedPhotons", str(resolved.output_hdf5))

    def test_resolve_transport_paths_preserves_sub_run_suffix_from_input_filename(self) -> None:
        """Explicit transport input filename should drive the default output suffix."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._build_config(Path(tmp_dir), sub_run_number=2)
            resolved = self.resolve_transport_paths(
                config,
                input_filename="photon_optical_interface_hits_0042.h5",
            )

            self.assertTrue(str(resolved.input_hdf5).endswith("photon_optical_interface_hits_0042.h5"))
            self.assertTrue(str(resolved.output_hdf5).endswith("photons_intensifier_hits_0042.h5"))

    def test_transport_from_sim_config_writes_only_reached_hits(self) -> None:
        """Transport should preserve linkage IDs and write only reached hits."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._build_config(Path(tmp_dir))
            resolved = self.resolve_transport_paths(config)
            self._write_input_hdf5(resolved.input_hdf5)

            summary = self.transport_from_sim_config(
                config,
                tracer=_StubTracer(),
                overwrite=True,
            )

            self.assertEqual(summary.total_photons, 2)
            self.assertEqual(summary.transported_photons, 1)
            self.assertEqual(summary.missed_photons, 1)
            self.assertEqual(summary.output_hdf5, resolved.output_hdf5)
            self.assertEqual(summary.ray_engine, "stub-tracer")

            with self.h5py.File(summary.output_hdf5, "r") as handle:
                self.assertIn("primaries", handle)
                self.assertIn("secondaries", handle)
                self.assertIn("transported_photons", handle)
                self.assertIn("secondary_end_x_mm", handle["secondaries"].dtype.names)
                self.assertIn("secondary_end_y_mm", handle["secondaries"].dtype.names)
                self.assertIn("secondary_end_z_mm", handle["secondaries"].dtype.names)

                rows = handle["transported_photons"][:]
                self.assertEqual(len(rows), 1)
                self.assertListEqual(rows["source_photon_index"].tolist(), [0])
                self.assertListEqual(rows["photon_track_id"].tolist(), [100])
                self.assertNotIn("optical_interface_hit_x_mm", rows.dtype.names)
                self.assertNotIn("optical_interface_hit_y_mm", rows.dtype.names)
                self.assertNotIn("optical_interface_hit_dir_x", rows.dtype.names)
                self.assertNotIn("optical_interface_hit_dir_y", rows.dtype.names)
                self.assertNotIn("optical_interface_hit_dir_z", rows.dtype.names)
                self.assertNotIn("optical_interface_hit_energy_eV", rows.dtype.names)
                self.assertNotIn("optical_interface_hit_wavelength_nm", rows.dtype.names)

                self.assertFalse(bool(rows["in_bounds"][0]))
                self.assertAlmostEqual(float(rows["intensifier_hit_x_mm"][0]), 11.5)
                self.assertAlmostEqual(float(rows["intensifier_hit_y_mm"][0]), -3.0)
                self.assertAlmostEqual(float(rows["intensifier_hit_z_mm"][0]), 42.0)

                self.assertEqual(handle.attrs["transport_engine"], "stub-tracer")
                self.assertIn("source_hdf5", handle.attrs)
                self.assertIn("lens_zmx_path", handle.attrs)
                self.assertTrue(bool(handle.attrs["intensifier_input_screen_defined"]))
                self.assertAlmostEqual(
                    float(handle.attrs["intensifier_input_screen_diameter_mm"]),
                    18.0,
                )
                self.np.testing.assert_allclose(
                    self.np.asarray(handle.attrs["intensifier_input_screen_center_mm"]),
                    self.np.array([0.0, 0.0]),
                )
                self.assertIn("generated_utc", handle.attrs)

    def test_transport_rejects_same_input_and_output_paths(self) -> None:
        """Input and output paths must be distinct to avoid accidental clobber."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._build_config(Path(tmp_dir))
            resolved = self.resolve_transport_paths(config)
            self._write_input_hdf5(resolved.input_hdf5)

            with self.assertRaises(ValueError):
                self.transport_from_sim_config(
                    config,
                    input_hdf5_path=resolved.input_hdf5,
                    output_hdf5_path=resolved.input_hdf5,
                    tracer=_StubTracer(),
                )

    def test_transport_uses_configured_chunk_rows(self) -> None:
        """Configured `TransportChunkRows` should drive HDF5 dataset chunking."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._build_config(Path(tmp_dir), transport_chunk_rows=1)
            resolved = self.resolve_transport_paths(config)
            self._write_input_hdf5(resolved.input_hdf5)

            summary = self.transport_from_sim_config(
                config,
                tracer=_StubTracer(),
                overwrite=True,
            )

            with self.h5py.File(summary.output_hdf5, "r") as handle:
                rows = handle["transported_photons"]
                self.assertEqual(rows.chunks, (1,))
                self.assertEqual(int(handle.attrs["transport_chunk_rows"]), 1)

    def test_transport_marks_reached_hits_in_bounds_without_screen_config(self) -> None:
        """When no input-screen geometry is configured, reached hits are in-bounds."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._build_config(
                Path(tmp_dir),
                include_intensifier_screen=False,
            )
            resolved = self.resolve_transport_paths(config)
            self._write_input_hdf5(resolved.input_hdf5)

            summary = self.transport_from_sim_config(
                config,
                tracer=_StubTracer(),
                overwrite=True,
            )

            with self.h5py.File(summary.output_hdf5, "r") as handle:
                rows = handle["transported_photons"][:]
                self.assertTrue(bool(rows["in_bounds"][0]))
                self.assertEqual(len(rows), 1)
                self.assertFalse(bool(handle.attrs["intensifier_input_screen_defined"]))

    def test_transport_logs_summary_to_run_log_when_logger_configured(self) -> None:
        """Transport should append major summary messages to the canonical run log."""

        if importlib.util.find_spec("loguru") is None:
            raise unittest.SkipTest("loguru is not installed in this test environment.")

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._build_config(Path(tmp_dir))
            resolved = self.resolve_transport_paths(config)
            self._write_input_hdf5(resolved.input_hdf5)

            screen_capture = io.StringIO()
            log_path = self.configure_run_logger(config, screen_sink=screen_capture)
            summary = self.transport_from_sim_config(
                config,
                tracer=_StubTracer(),
                overwrite=True,
            )

            screen_output = screen_capture.getvalue()
            file_output = log_path.read_text(encoding="utf-8")

            self.assertIn("Starting optical transport", screen_output)
            self.assertIn("Transport finished", screen_output)
            self.assertIn(str(summary.output_hdf5), screen_output)
            self.assertIn("Loaded 2 photons for transport.", file_output)
            self.assertIn("Transport chunk rows:", file_output)
            self.assertIn(str(summary.output_hdf5), file_output)

    def test_transport_writes_terminal_progress_bar_by_processed_photons(self) -> None:
        """Transport should render a chunk-based terminal progress bar."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._build_config(Path(tmp_dir), transport_chunk_rows=1)
            resolved = self.resolve_transport_paths(config)
            self._write_input_hdf5(resolved.input_hdf5)

            with patch(
                "src.optics.OpticalTransport.sys.stderr",
                new=io.StringIO(),
            ) as stderr_capture:
                summary = self.transport_from_sim_config(
                    config,
                    tracer=_StubTracer(),
                    overwrite=True,
                )

            terminal_output = stderr_capture.getvalue()
            self.assertEqual(summary.total_photons, 2)
            self.assertIn("Transport", terminal_output)
            self.assertIn("(1/2 photons)", terminal_output)
            self.assertIn("(2/2 photons)", terminal_output)
            self.assertIn("100%", terminal_output)

    def test_transport_suppresses_terminal_progress_when_disabled(self) -> None:
        """Transport should not emit progress-bar lines when disabled in config."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._build_config(Path(tmp_dir), transport_chunk_rows=1)
            config.optical.show_transport_progress = False
            resolved = self.resolve_transport_paths(config)
            self._write_input_hdf5(resolved.input_hdf5)

            with patch(
                "src.optics.OpticalTransport.sys.stderr",
                new=io.StringIO(),
            ) as stderr_capture:
                summary = self.transport_from_sim_config(
                    config,
                    tracer=_StubTracer(),
                    overwrite=True,
                )

            terminal_output = stderr_capture.getvalue()
            self.assertEqual(summary.total_photons, 2)
            self.assertNotIn("(1/2 photons)", terminal_output)
            self.assertNotIn("(2/2 photons)", terminal_output)


if __name__ == "__main__":
    unittest.main()
