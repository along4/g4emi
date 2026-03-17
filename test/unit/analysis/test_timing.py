"""Unit tests for timing analysis helpers."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from test.unit.analysis._support import AnalysisDataBuilderMixin, AnalysisTestCase


class TimingAnalysisTests(AnalysisDataBuilderMixin, AnalysisTestCase):
    """Validate timing extraction, rendering, and fitting helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        from analysis.timing import (
            ScintillationDecayComponent,
            decay_model_bin_counts,
            fit_photon_creation_delay_histogram,
            photon_creation_delays_ns,
            photon_creation_delay_to_histogram,
        )
        import analysis.timing as timing_module

        cls.ScintillationDecayComponent = ScintillationDecayComponent
        cls.decay_model_bin_counts = staticmethod(decay_model_bin_counts)
        cls.fit_photon_creation_delay_histogram = staticmethod(
            fit_photon_creation_delay_histogram
        )
        cls.photon_creation_delays_ns = staticmethod(photon_creation_delays_ns)
        cls.photon_creation_delay_to_histogram = staticmethod(
            photon_creation_delay_to_histogram
        )
        cls.scipy_available = timing_module.least_squares is not None

    def test_photon_creation_delay_histogram_uses_primary_interaction_times(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hdf5_path = Path(tmp_dir) / "photon_optical_interface_hits.h5"
            self._write_timing_hdf5(hdf5_path)

            fig, ax = self.photon_creation_delay_to_histogram(
                hdf5_path,
                bins=[0.0, 2.5, 5.5, 8.5],
                log_scale=False,
                show=False,
            )

            counts = [float(patch.get_height()) for patch in ax.patches]
            self.assertEqual(sum(counts), 2.0)
            self.assertEqual(ax.get_xlabel(), "delay (ns)")
            self.assertEqual(ax.get_ylabel(), "counts")
            self.assertIn("Primary Interaction", ax.get_title())
            self.plt.close(fig)

    def test_photon_creation_delays_extract_expected_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hdf5_path = Path(tmp_dir) / "photon_optical_interface_hits.h5"
            self._write_timing_hdf5(hdf5_path)

            delays_ns = self.photon_creation_delays_ns(hdf5_path)

            self.assertTrue(
                self.np.allclose(
                    self.np.sort(delays_ns),
                    self.np.array([2.0, 5.0], dtype=float),
                )
            )

    def test_photon_creation_delay_fit_recovers_three_component_model(self) -> None:
        if not self.scipy_available:
            raise unittest.SkipTest(
                "scipy is unavailable; skipping timing-fit recovery test."
            )
        with tempfile.TemporaryDirectory() as tmp_dir:
            rng = self.np.random.default_rng(12345)
            true_components = (
                self.ScintillationDecayComponent(1.5, 0.6),
                self.ScintillationDecayComponent(6.0, 0.3),
                self.ScintillationDecayComponent(25.0, 0.1),
            )
            component_index = rng.choice(
                3,
                size=60000,
                p=[component.yield_fraction for component in true_components],
            )
            delays_ns = self.np.empty(component_index.size, dtype=float)
            for index, component in enumerate(true_components):
                mask = component_index == index
                delays_ns[mask] = rng.exponential(
                    scale=component.time_constant_ns,
                    size=int(self.np.count_nonzero(mask)),
                )

            hdf5_path = Path(tmp_dir) / "photon_optical_interface_hits.h5"
            self._write_delay_sample_hdf5(hdf5_path, delays_ns)

            fit_result = self.fit_photon_creation_delay_histogram(
                hdf5_path,
                bins=self.np.linspace(0.0, 60.0, 121),
                initial_components=(
                    self.ScintillationDecayComponent(1.0, 0.5),
                    self.ScintillationDecayComponent(5.0, 0.35),
                    self.ScintillationDecayComponent(20.0, 0.15),
                ),
            )

            fitted_components = fit_result.components
            self.assertEqual(len(fitted_components), 3)
            expected_taus = [1.5, 6.0, 25.0]
            expected_yields = [0.6, 0.3, 0.1]
            for fitted, expected_tau, expected_yield in zip(
                fitted_components,
                expected_taus,
                expected_yields,
                strict=False,
            ):
                self.assertAlmostEqual(
                    fitted.time_constant_ns,
                    expected_tau,
                    delta=expected_tau * 0.25,
                )
                self.assertAlmostEqual(
                    fitted.yield_fraction,
                    expected_yield,
                    delta=0.08,
                )
            self.assertEqual(len(fit_result.observed_counts), 120)
            self.assertEqual(len(fit_result.fitted_counts), 120)
            self.assertLess(fit_result.rmse_counts, 80.0)

    def test_decay_model_accepts_zero_yield_inactive_components(self) -> None:
        counts = self.decay_model_bin_counts(
            [0.0, 1.0, 2.0],
            total_count=100.0,
            components=(
                self.ScintillationDecayComponent(2.1, 1.0),
                self.ScintillationDecayComponent(0.0, 0.0),
                self.ScintillationDecayComponent(0.0, 0.0),
            ),
        )
        self.assertEqual(len(counts), 2)
        self.assertTrue(self.np.all(counts >= 0.0))

    def test_timing_fit_rejects_invalid_initial_components(self) -> None:
        if not self.scipy_available:
            raise unittest.SkipTest(
                "scipy is unavailable; skipping timing-fit validation test."
            )
        with tempfile.TemporaryDirectory() as tmp_dir:
            hdf5_path = Path(tmp_dir) / "photon_optical_interface_hits.h5"
            self._write_timing_hdf5(hdf5_path)

            with self.assertRaisesRegex(
                ValueError,
                "Yield fractions must be non-negative.",
            ):
                self.fit_photon_creation_delay_histogram(
                    hdf5_path,
                    initial_components=(
                        self.ScintillationDecayComponent(1.0, 0.8),
                        self.ScintillationDecayComponent(2.0, -0.1),
                        self.ScintillationDecayComponent(3.0, 0.3),
                    ),
                )
