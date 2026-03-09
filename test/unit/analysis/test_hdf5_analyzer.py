"""Unit tests for lightweight HDF5 analyzer intensifier plotting behavior."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


def _repo_root() -> Path:
    """Resolve repository root by searching parent directories."""

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "analysis").is_dir() and (parent / "pixi.toml").is_file():
            return parent
    raise RuntimeError("Could not resolve repository root from test path.")


sys.path.insert(0, str(_repo_root()))


class IntensifierPlotTests(unittest.TestCase):
    """Validate fixed plotting extents from intensifier screen metadata."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import h5py
            import matplotlib
            import numpy as np

            matplotlib.use("Agg")
            from matplotlib import pyplot as plt

            from analysis.hdf5Analyzer import (
                ScintillationDecayComponent,
                decay_model_bin_counts,
                fit_photon_creation_delay_histogram,
                intensifier_photons_to_image,
                photon_creation_delays_ns,
                photon_creation_delay_to_histogram,
                photon_exit_to_image,
                photon_origins_to_image,
            )
            import analysis.hdf5Analyzer as analyzer_module
        except ModuleNotFoundError as exc:
            missing = (getattr(exc, "name", "") or "").lower()
            if missing in {"h5py", "numpy", "matplotlib"}:
                raise unittest.SkipTest(
                    f"Missing dependency for analyzer tests: {exc}. "
                    "Run in the project environment (for example: pixi run test-python)."
                ) from exc
            raise

        cls.h5py = h5py
        cls.np = np
        cls.plt = plt
        cls.ScintillationDecayComponent = ScintillationDecayComponent
        cls.scipy_available = analyzer_module.least_squares is not None
        cls.decay_model_bin_counts = staticmethod(decay_model_bin_counts)
        cls.fit_photon_creation_delay_histogram = staticmethod(
            fit_photon_creation_delay_histogram
        )
        cls.intensifier_photons_to_image = staticmethod(intensifier_photons_to_image)
        cls.photon_creation_delays_ns = staticmethod(photon_creation_delays_ns)
        cls.photon_creation_delay_to_histogram = staticmethod(
            photon_creation_delay_to_histogram
        )
        cls.photon_origins_to_image = staticmethod(photon_origins_to_image)
        cls.photon_exit_to_image = staticmethod(photon_exit_to_image)
        cls.analyzer_module = analyzer_module

    def _write_transport_hdf5(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        dtype = self.np.dtype(
            [
                ("intensifier_hit_x_mm", self.np.float64),
                ("intensifier_hit_y_mm", self.np.float64),
                ("reached_intensifier", self.np.bool_),
                ("in_bounds", self.np.bool_),
            ]
        )
        rows = self.np.array(
            [
                (0.0, 0.0, True, True),
                (10.0, 0.0, True, False),
                (self.np.nan, self.np.nan, False, False),
            ],
            dtype=dtype,
        )
        with self.h5py.File(path, "w") as handle:
            handle.create_dataset("transported_photons", data=rows)
            handle.attrs["intensifier_input_screen_defined"] = True
            handle.attrs["intensifier_input_screen_diameter_mm"] = 18.0
            handle.attrs["intensifier_input_screen_center_mm"] = self.np.array(
                [0.0, 0.0],
                dtype=self.np.float64,
            )
            handle.attrs["intensifier_input_screen_coordinate_frame"] = (
                "intensifier_input_plane"
            )

    def _write_photons_hdf5(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        dtype = self.np.dtype(
            [
                ("photon_origin_x_mm", self.np.float64),
                ("photon_origin_y_mm", self.np.float64),
                ("photon_scint_exit_x_mm", self.np.float64),
                ("photon_scint_exit_y_mm", self.np.float64),
            ]
        )
        rows = self.np.array(
            [
                (0.5, -0.5, 1.0, 1.0),
                (-1.0, 0.75, self.np.nan, self.np.nan),
            ],
            dtype=dtype,
        )
        with self.h5py.File(path, "w") as handle:
            handle.create_dataset("photons", data=rows)

    def _write_timing_hdf5(self, path: Path, *, legacy_field_name: bool) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        interaction_field = (
            "primary_t0_time_ns" if legacy_field_name else "primary_interaction_time_ns"
        )
        primaries_dtype = self.np.dtype(
            [
                ("gun_call_id", self.np.int64),
                ("primary_track_id", self.np.int32),
                (interaction_field, self.np.float64),
            ]
        )
        photons_dtype = self.np.dtype(
            [
                ("gun_call_id", self.np.int64),
                ("primary_track_id", self.np.int32),
                ("photon_creation_time_ns", self.np.float64),
            ]
        )
        primary_rows = self.np.array(
            [
                (0, 11, 3.0),
                (0, 12, self.np.nan),
            ],
            dtype=primaries_dtype,
        )
        photon_rows = self.np.array(
            [
                (0, 11, 5.0),
                (0, 11, 8.0),
                (0, 12, 9.0),
                (0, 99, 4.0),
            ],
            dtype=photons_dtype,
        )
        with self.h5py.File(path, "w") as handle:
            handle.create_dataset("primaries", data=primary_rows)
            handle.create_dataset("photons", data=photon_rows)

    def _write_delay_sample_hdf5(self, path: Path, delays_ns: np.ndarray) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        primaries_dtype = self.np.dtype(
            [
                ("gun_call_id", self.np.int64),
                ("primary_track_id", self.np.int32),
                ("primary_interaction_time_ns", self.np.float64),
            ]
        )
        photons_dtype = self.np.dtype(
            [
                ("gun_call_id", self.np.int64),
                ("primary_track_id", self.np.int32),
                ("photon_creation_time_ns", self.np.float64),
            ]
        )
        primary_rows = self.np.array([(0, 1, 0.0)], dtype=primaries_dtype)
        photon_rows = self.np.array(
            [(0, 1, float(delay_ns)) for delay_ns in delays_ns],
            dtype=photons_dtype,
        )
        with self.h5py.File(path, "w") as handle:
            handle.create_dataset("primaries", data=primary_rows)
            handle.create_dataset("photons", data=photon_rows)

    def test_intensifier_plot_uses_image_circle_extent_and_reports_oob(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hdf5_path = Path(tmp_dir) / "photons_intensifier_hits.h5"
            self._write_transport_hdf5(hdf5_path)

            fig, ax = self.intensifier_photons_to_image(
                hdf5_path,
                bins=(32, 32),
                show=False,
            )

            x_lim = ax.get_xlim()
            y_lim = ax.get_ylim()
            self.assertAlmostEqual(float(x_lim[0]), -9.0)
            self.assertAlmostEqual(float(x_lim[1]), 9.0)
            self.assertAlmostEqual(float(y_lim[0]), -9.0)
            self.assertAlmostEqual(float(y_lim[1]), 9.0)
            self.assertIn("out-of-bounds: 50.0%", ax.get_title())
            self.assertEqual(len(ax.patches), 1)
            self.plt.close(fig)

    def test_photon_origin_and_exit_use_scintillator_extent_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hdf5_path = Path(tmp_dir) / "photon_optical_interface_hits.h5"
            self._write_photons_hdf5(hdf5_path)
            expected_range = ((-25.0, 25.0), (-10.0, 10.0))

            with mock.patch.object(
                self.analyzer_module,
                "_scintillator_xy_range_from_sim_config",
                return_value=expected_range,
            ):
                fig1, ax1 = self.photon_origins_to_image(
                    hdf5_path,
                    bins=(32, 32),
                    sim_config_yaml_path=Path("/tmp/sim.yaml"),
                    show=False,
                )
                fig2, ax2 = self.photon_exit_to_image(
                    hdf5_path,
                    bins=(32, 32),
                    sim_config_yaml_path=Path("/tmp/sim.yaml"),
                    show=False,
                )

            self.assertAlmostEqual(float(ax1.get_xlim()[0]), -25.0)
            self.assertAlmostEqual(float(ax1.get_xlim()[1]), 25.0)
            self.assertAlmostEqual(float(ax1.get_ylim()[0]), -10.0)
            self.assertAlmostEqual(float(ax1.get_ylim()[1]), 10.0)
            self.assertAlmostEqual(float(ax2.get_xlim()[0]), -25.0)
            self.assertAlmostEqual(float(ax2.get_xlim()[1]), 25.0)
            self.assertAlmostEqual(float(ax2.get_ylim()[0]), -10.0)
            self.assertAlmostEqual(float(ax2.get_ylim()[1]), 10.0)
            self.plt.close(fig1)
            self.plt.close(fig2)

    def test_photon_creation_delay_histogram_uses_primary_interaction_times(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hdf5_path = Path(tmp_dir) / "photon_optical_interface_hits.h5"
            self._write_timing_hdf5(hdf5_path, legacy_field_name=False)

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
            self._write_timing_hdf5(hdf5_path, legacy_field_name=False)

            delays_ns = self.photon_creation_delays_ns(hdf5_path)

            self.assertTrue(
                self.np.allclose(
                    self.np.sort(delays_ns),
                    self.np.array([2.0, 5.0], dtype=float),
                )
            )

    def test_photon_creation_delay_histogram_accepts_legacy_primary_time_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hdf5_path = Path(tmp_dir) / "photon_optical_interface_hits.h5"
            self._write_timing_hdf5(hdf5_path, legacy_field_name=True)

            fig, ax = self.photon_creation_delay_to_histogram(
                hdf5_path,
                bins=[0.0, 2.5, 5.5, 8.5],
                log_scale=False,
                show=False,
            )

            counts = [float(patch.get_height()) for patch in ax.patches]
            self.assertEqual(sum(counts), 2.0)
            self.plt.close(fig)

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
            self._write_timing_hdf5(hdf5_path, legacy_field_name=False)

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


if __name__ == "__main__":
    unittest.main()
