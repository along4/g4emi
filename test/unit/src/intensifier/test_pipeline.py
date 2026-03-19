"""Unit tests for end-to-end intensifier pipeline execution."""

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


class IntensifierPipelineTests(unittest.TestCase):
    """Validate end-to-end stage composition for the intensifier module."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from src.intensifier.models import IntensifierParams
            from src.intensifier.models import McpParams
            from src.intensifier.models import PhotocathodeParams
            from src.intensifier.models import PhosphorParams
            from src.intensifier.models import TransportedPhotonBatch
            from src.intensifier.pipeline import IntensifierPipeline
            from src.intensifier.pipeline import run_intensifier_pipeline
        except ModuleNotFoundError as exc:
            missing = (getattr(exc, "name", "") or "").lower()
            if missing in {"numpy"}:
                raise unittest.SkipTest(
                    f"Missing dependency for intensifier tests: {exc}. "
                    "Run in the project environment (for example: pixi run test-python)."
                ) from exc
            raise

        cls.IntensifierParams = IntensifierParams
        cls.McpParams = McpParams
        cls.PhotocathodeParams = PhotocathodeParams
        cls.PhosphorParams = PhosphorParams
        cls.TransportedPhotonBatch = TransportedPhotonBatch
        cls.IntensifierPipeline = IntensifierPipeline
        cls.run_intensifier_pipeline = staticmethod(run_intensifier_pipeline)

    def _photons(self) -> object:
        """Build a small deterministic transported-photon batch."""

        return self.TransportedPhotonBatch(
            source_photon_index=np.array([0, 1, 2], dtype=np.int64),
            gun_call_id=np.array([10, 10, 11], dtype=np.int64),
            primary_track_id=np.array([100, 100, 101], dtype=np.int32),
            secondary_track_id=np.array([200, 201, 202], dtype=np.int32),
            photon_track_id=np.array([300, 301, 302], dtype=np.int32),
            x_mm=np.array([1.0, 2.0, 3.0], dtype=np.float64),
            y_mm=np.array([-1.0, -2.0, -3.0], dtype=np.float64),
            z_mm=np.array([0.5, 0.5, 0.5], dtype=np.float64),
            time_ns=np.array([5.0, 6.0, 7.0], dtype=np.float64),
            wavelength_nm=np.array([400.0, 500.0, 650.0], dtype=np.float64),
        )

    def _params(self) -> object:
        """Build a deterministic intensifier parameter bundle."""

        return self.IntensifierParams(
            photocathode=self.PhotocathodeParams(
                qe_wavelength_nm=np.array([350.0, 700.0], dtype=np.float64),
                qe_values=np.array([1.0, 1.0], dtype=np.float64),
                collection_efficiency=1.0,
                tts_sigma_ns=0.0,
            ),
            mcp=self.McpParams(
                stage1_mean_gain=10.0,
                stage1_gain_shape=2.0,
                stage2_mean_gain=100.0,
                stage2_gain_shape=2.0,
                gain_ref=1000.0,
                spread_sigma0_mm=0.0,
                spread_gain_exponent=0.4,
            ),
            phosphor=self.PhosphorParams(
                phosphor_gain=1.0,
                decay_fast_ns=70.0,
                decay_slow_ns=200.0,
                fast_fraction=1.0,
                psf_sigma_mm=0.0,
            ),
        )

    def test_run_intensifier_pipeline_preserves_batch_size_with_unit_detection(self) -> None:
        photons = self._photons()
        params = self._params()

        result = self.run_intensifier_pipeline(
            photons,
            params,
            rng=np.random.default_rng(123),
        )

        self.assertEqual(len(result), len(photons))
        np.testing.assert_array_equal(result.source_photon_index, photons.source_photon_index)
        np.testing.assert_array_equal(result.gun_call_id, photons.gun_call_id)
        np.testing.assert_array_equal(result.primary_track_id, photons.primary_track_id)
        np.testing.assert_array_equal(result.secondary_track_id, photons.secondary_track_id)
        np.testing.assert_array_equal(result.photon_track_id, photons.photon_track_id)
        self.assertTrue(np.all(result.output_time_ns >= photons.time_ns))
        self.assertTrue(np.all(result.signal_amplitude_arb > 0.0))

    def test_pipeline_wrapper_runs_same_flow(self) -> None:
        photons = self._photons()
        params = self._params()
        pipeline = self.IntensifierPipeline(params=params)

        result = pipeline.run(
            photons,
            rng=np.random.default_rng(123),
        )

        self.assertEqual(len(result), len(photons))
        np.testing.assert_array_equal(result.source_photon_index, photons.source_photon_index)


if __name__ == "__main__":
    unittest.main()
