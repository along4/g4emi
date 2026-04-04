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
            from src.intensifier.models import IntensifierOutputBatch
            from src.sensor.models import TimepixEventBatch
            from src.sensor.models import TimepixHitBatch
            from src.sensor.models import TimepixParams
            from src.sensor.timepix import centered_mm_to_pixel_indices
            from src.sensor.timepix import compute_timepix_sensor_size_mm
            from src.sensor.timepix import convert_timepix_events_to_hits
            from src.sensor.timepix import map_intensifier_output_to_timepix_events
            from src.sensor.timepix import sort_timepix_events_by_time
            from src.sensor.timepix import timepix_params_from_sim_config
            from src.sensor.timepix import timepix_in_bounds_mask
        except ModuleNotFoundError as exc:
            missing = (getattr(exc, "name", "") or "").lower()
            if missing in {"numpy", "pydantic"}:
                raise unittest.SkipTest(
                    f"Missing dependency for sensor tests: {exc}. "
                    "Run in the project environment (for example: pixi run test-python)."
                ) from exc
            raise

        cls.SimConfig = SimConfig
        cls.IntensifierOutputBatch = IntensifierOutputBatch
        cls.TimepixEventBatch = TimepixEventBatch
        cls.TimepixHitBatch = TimepixHitBatch
        cls.TimepixParams = TimepixParams
        cls.centered_mm_to_pixel_indices = staticmethod(centered_mm_to_pixel_indices)
        cls.compute_timepix_sensor_size_mm = staticmethod(compute_timepix_sensor_size_mm)
        cls.convert_timepix_events_to_hits = staticmethod(convert_timepix_events_to_hits)
        cls.map_intensifier_output_to_timepix_events = staticmethod(
            map_intensifier_output_to_timepix_events
        )
        cls.sort_timepix_events_by_time = staticmethod(sort_timepix_events_by_time)
        cls.timepix_params_from_sim_config = staticmethod(timepix_params_from_sim_config)
        cls.timepix_in_bounds_mask = staticmethod(timepix_in_bounds_mask)

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

    def _intensifier_output(self) -> object:
        """Build a deterministic intensifier output batch for sensor mapping tests."""

        return self.IntensifierOutputBatch(
            source_photon_index=np.array([0, 1, 2, 3], dtype=np.int64),
            gun_call_id=np.array([10, 10, 11, 12], dtype=np.int64),
            primary_track_id=np.array([100, 100, 101, 102], dtype=np.int32),
            secondary_track_id=np.array([200, 201, 202, 203], dtype=np.int32),
            photon_track_id=np.array([300, 301, 302, 303], dtype=np.int32),
            output_x_mm=np.array([-1.9, -0.1, 0.1, 2.0], dtype=np.float64),
            output_y_mm=np.array([0.0, -0.9, 0.9, 0.0], dtype=np.float64),
            output_time_ns=np.array([5.0, 6.0, 7.0, 8.0], dtype=np.float64),
            signal_amplitude_arb=np.array([10.0, 20.0, 30.0, 40.0], dtype=np.float64),
            total_gain=np.array([100.0, 200.0, 300.0, 400.0], dtype=np.float64),
            wavelength_nm=np.array([400.0, 500.0, 600.0, 700.0], dtype=np.float64),
        )

    def _timepix_events(self) -> object:
        """Build a deterministic mapped-event batch for readout tests."""

        return self.TimepixEventBatch(
            source_photon_index=np.array([0, 1, 2, 3, 4], dtype=np.int64),
            gun_call_id=np.array([10, 11, 12, 13, 14], dtype=np.int64),
            primary_track_id=np.array([100, 101, 102, 103, 104], dtype=np.int32),
            secondary_track_id=np.array([200, 201, 202, 203, 204], dtype=np.int32),
            photon_track_id=np.array([300, 301, 302, 303, 304], dtype=np.int32),
            x_pixel=np.array([1, 1, 1, 2, 1], dtype=np.int32),
            y_pixel=np.array([2, 2, 2, 2, 2], dtype=np.int32),
            event_time_ns=np.array([10.0, 12.0, 30.0, 13.0, 50.0], dtype=np.float64),
            signal_amplitude_arb=np.array([5.0, 4.0, 6.0, 8.0, 7.0], dtype=np.float64),
        )

    def test_timepix_params_reject_negative_dead_time(self) -> None:
        with self.assertRaises(ValueError):
            self.TimepixParams(
                pixels_x=256,
                pixels_y=256,
                pixel_pitch_mm=0.055,
                max_tot_ns=25550.0,
                dead_time_ns=-1.0,
            )

    def test_timepix_event_batch_empty_has_expected_dtypes(self) -> None:
        batch = self.TimepixEventBatch.empty()

        self.assertEqual(len(batch), 0)
        self.assertEqual(batch.source_photon_index.dtype, np.int64)
        self.assertEqual(batch.x_pixel.dtype, np.int32)
        self.assertEqual(batch.event_time_ns.dtype, np.float64)

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

    def test_compute_timepix_sensor_size_mm_matches_single_timepix3(self) -> None:
        params = self.TimepixParams(
            pixels_x=256,
            pixels_y=256,
            pixel_pitch_mm=0.055,
            max_tot_ns=25550.0,
            dead_time_ns=475.0,
        )

        sensor_width_mm, sensor_height_mm = self.compute_timepix_sensor_size_mm(params)

        self.assertAlmostEqual(sensor_width_mm, 14.08)
        self.assertAlmostEqual(sensor_height_mm, 14.08)

    def test_timepix_in_bounds_mask_uses_centered_half_open_bounds(self) -> None:
        params = self.TimepixParams(
            pixels_x=4,
            pixels_y=2,
            pixel_pitch_mm=1.0,
            max_tot_ns=25550.0,
            dead_time_ns=475.0,
        )
        intensifier_output = self.IntensifierOutputBatch(
            source_photon_index=np.array([0, 1, 2, 3, 4, 5], dtype=np.int64),
            gun_call_id=np.array([10, 11, 12, 13, 14, 15], dtype=np.int64),
            primary_track_id=np.array([100, 101, 102, 103, 104, 105], dtype=np.int32),
            secondary_track_id=np.array([200, 201, 202, 203, 204, 205], dtype=np.int32),
            photon_track_id=np.array([300, 301, 302, 303, 304, 305], dtype=np.int32),
            output_x_mm=np.array([-2.0, 1.999, 2.0, 0.0, 0.0, 0.0], dtype=np.float64),
            output_y_mm=np.array([0.0, 0.0, 0.0, -1.0, 0.999, 1.0], dtype=np.float64),
            output_time_ns=np.zeros(6, dtype=np.float64),
            signal_amplitude_arb=np.ones(6, dtype=np.float64),
            total_gain=np.ones(6, dtype=np.float64),
            wavelength_nm=np.full(6, 500.0, dtype=np.float64),
        )

        mask = self.timepix_in_bounds_mask(intensifier_output, params)

        np.testing.assert_array_equal(
            mask,
            np.array([True, True, False, True, True, False], dtype=bool),
        )

    def test_centered_mm_to_pixel_indices_maps_edges_correctly(self) -> None:
        params = self.TimepixParams(
            pixels_x=4,
            pixels_y=2,
            pixel_pitch_mm=1.0,
            max_tot_ns=25550.0,
            dead_time_ns=475.0,
        )

        x_pixel, y_pixel = self.centered_mm_to_pixel_indices(
            np.array([-2.0, -1.01, -0.01, 0.99, 1.999], dtype=np.float64),
            np.array([-1.0, -0.01, 0.0, 0.5, 0.999], dtype=np.float64),
            params,
        )

        np.testing.assert_array_equal(x_pixel, np.array([0, 0, 1, 2, 3], dtype=np.int32))
        np.testing.assert_array_equal(y_pixel, np.array([0, 0, 1, 1, 1], dtype=np.int32))

    def test_map_intensifier_output_to_timepix_events_drops_out_of_bounds(self) -> None:
        params = self.TimepixParams(
            pixels_x=4,
            pixels_y=2,
            pixel_pitch_mm=1.0,
            max_tot_ns=25550.0,
            dead_time_ns=475.0,
        )

        result = self.map_intensifier_output_to_timepix_events(
            self._intensifier_output(),
            params,
        )

        self.assertEqual(len(result), 3)
        np.testing.assert_array_equal(result.source_photon_index, np.array([0, 1, 2], dtype=np.int64))
        np.testing.assert_array_equal(result.x_pixel, np.array([0, 1, 2], dtype=np.int32))
        np.testing.assert_array_equal(result.y_pixel, np.array([1, 0, 1], dtype=np.int32))
        np.testing.assert_allclose(result.event_time_ns, np.array([5.0, 6.0, 7.0], dtype=np.float64))
        np.testing.assert_allclose(
            result.signal_amplitude_arb,
            np.array([10.0, 20.0, 30.0], dtype=np.float64),
        )

    def test_map_intensifier_output_to_timepix_events_handles_empty_input(self) -> None:
        params = self.TimepixParams(
            pixels_x=256,
            pixels_y=256,
            pixel_pitch_mm=0.055,
            max_tot_ns=25550.0,
            dead_time_ns=475.0,
        )

        result = self.map_intensifier_output_to_timepix_events(
            self.IntensifierOutputBatch.empty(),
            params,
        )

        self.assertEqual(len(result), 0)
        self.assertEqual(result.x_pixel.dtype, np.int32)
        self.assertEqual(result.event_time_ns.dtype, np.float64)

    def test_sort_timepix_events_by_time_is_stable(self) -> None:
        events = self.TimepixEventBatch(
            source_photon_index=np.array([0, 1, 2], dtype=np.int64),
            gun_call_id=np.array([10, 11, 12], dtype=np.int64),
            primary_track_id=np.array([100, 101, 102], dtype=np.int32),
            secondary_track_id=np.array([200, 201, 202], dtype=np.int32),
            photon_track_id=np.array([300, 301, 302], dtype=np.int32),
            x_pixel=np.array([1, 1, 1], dtype=np.int32),
            y_pixel=np.array([2, 2, 2], dtype=np.int32),
            event_time_ns=np.array([7.0, 5.0, 5.0], dtype=np.float64),
            signal_amplitude_arb=np.array([1.0, 2.0, 3.0], dtype=np.float64),
        )

        result = self.sort_timepix_events_by_time(events)

        np.testing.assert_array_equal(
            result.source_photon_index,
            np.array([1, 2, 0], dtype=np.int64),
        )

    def test_convert_timepix_events_to_hits_merges_same_pixel_while_active(self) -> None:
        params = self.TimepixParams(
            pixels_x=256,
            pixels_y=256,
            pixel_pitch_mm=0.055,
            max_tot_ns=20.0,
            dead_time_ns=5.0,
        )

        result = self.convert_timepix_events_to_hits(self._timepix_events(), params)

        self.assertEqual(len(result), 3)
        np.testing.assert_array_equal(result.x_pixel, np.array([1, 2, 1], dtype=np.int32))
        np.testing.assert_array_equal(result.y_pixel, np.array([2, 2, 2], dtype=np.int32))
        np.testing.assert_allclose(
            result.time_over_threshold_ns,
            np.array([7.0, 8.0, 7.0], dtype=np.float64),
        )
        np.testing.assert_array_equal(
            result.contribution_count,
            np.array([2, 1, 1], dtype=np.int32),
        )
        np.testing.assert_allclose(result.time_of_arrival_ns, np.zeros(3, dtype=np.float64))
        np.testing.assert_array_equal(result.gun_call_id, np.array([10, 13, 14], dtype=np.int64))

    def test_convert_timepix_events_to_hits_clips_merged_tot_to_max(self) -> None:
        params = self.TimepixParams(
            pixels_x=256,
            pixels_y=256,
            pixel_pitch_mm=0.055,
            max_tot_ns=6.0,
            dead_time_ns=5.0,
        )
        events = self.TimepixEventBatch(
            source_photon_index=np.array([0, 1], dtype=np.int64),
            gun_call_id=np.array([10, 11], dtype=np.int64),
            primary_track_id=np.array([100, 101], dtype=np.int32),
            secondary_track_id=np.array([200, 201], dtype=np.int32),
            photon_track_id=np.array([300, 301], dtype=np.int32),
            x_pixel=np.array([1, 1], dtype=np.int32),
            y_pixel=np.array([2, 2], dtype=np.int32),
            event_time_ns=np.array([10.0, 12.0], dtype=np.float64),
            signal_amplitude_arb=np.array([5.0, 5.0], dtype=np.float64),
        )

        result = self.convert_timepix_events_to_hits(events, params)

        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result.time_over_threshold_ns[0], 6.0)
        self.assertEqual(result.contribution_count[0], 2)

    def test_convert_timepix_events_to_hits_drops_events_during_dead_time(self) -> None:
        params = self.TimepixParams(
            pixels_x=256,
            pixels_y=256,
            pixel_pitch_mm=0.055,
            max_tot_ns=20.0,
            dead_time_ns=10.0,
        )
        events = self.TimepixEventBatch(
            source_photon_index=np.array([0, 1], dtype=np.int64),
            gun_call_id=np.array([10, 11], dtype=np.int64),
            primary_track_id=np.array([100, 101], dtype=np.int32),
            secondary_track_id=np.array([200, 201], dtype=np.int32),
            photon_track_id=np.array([300, 301], dtype=np.int32),
            x_pixel=np.array([1, 1], dtype=np.int32),
            y_pixel=np.array([2, 2], dtype=np.int32),
            event_time_ns=np.array([10.0, 16.0], dtype=np.float64),
            signal_amplitude_arb=np.array([5.0, 4.0], dtype=np.float64),
        )

        result = self.convert_timepix_events_to_hits(events, params)

        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result.time_over_threshold_ns[0], 5.0)
        self.assertEqual(result.contribution_count[0], 1)

    def test_convert_timepix_events_to_hits_starts_new_hit_after_dead_time(self) -> None:
        params = self.TimepixParams(
            pixels_x=256,
            pixels_y=256,
            pixel_pitch_mm=0.055,
            max_tot_ns=20.0,
            dead_time_ns=5.0,
        )
        events = self.TimepixEventBatch(
            source_photon_index=np.array([0, 1], dtype=np.int64),
            gun_call_id=np.array([10, 11], dtype=np.int64),
            primary_track_id=np.array([100, 101], dtype=np.int32),
            secondary_track_id=np.array([200, 201], dtype=np.int32),
            photon_track_id=np.array([300, 301], dtype=np.int32),
            x_pixel=np.array([1, 1], dtype=np.int32),
            y_pixel=np.array([2, 2], dtype=np.int32),
            event_time_ns=np.array([10.0, 21.0], dtype=np.float64),
            signal_amplitude_arb=np.array([5.0, 4.0], dtype=np.float64),
        )

        result = self.convert_timepix_events_to_hits(events, params)

        self.assertEqual(len(result), 2)
        np.testing.assert_array_equal(result.gun_call_id, np.array([10, 11], dtype=np.int64))
        np.testing.assert_allclose(
            result.time_over_threshold_ns,
            np.array([5.0, 4.0], dtype=np.float64),
        )

    def test_convert_timepix_events_to_hits_handles_empty_input(self) -> None:
        params = self.TimepixParams(
            pixels_x=256,
            pixels_y=256,
            pixel_pitch_mm=0.055,
            max_tot_ns=25550.0,
            dead_time_ns=475.0,
        )

        result = self.convert_timepix_events_to_hits(self.TimepixEventBatch.empty(), params)

        self.assertEqual(len(result), 0)
        self.assertEqual(result.x_pixel.dtype, np.int32)

    def test_timepix_params_from_sim_config_requires_sensor(self) -> None:
        payload = self._config_payload()
        payload.pop("sensor")
        config = self.SimConfig.model_validate(payload)

        with self.assertRaises(ValueError):
            self.timepix_params_from_sim_config(config)


if __name__ == "__main__":
    unittest.main()
