"""Unit tests for spatial analysis helpers."""

from __future__ import annotations

from pathlib import Path
import tempfile
from unittest import mock

from test.unit.analysis._support import AnalysisDataBuilderMixin, AnalysisTestCase


class SpatialAnalysisTests(AnalysisDataBuilderMixin, AnalysisTestCase):
    """Validate spatial plotting helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        from analysis.spatial import (
            intensifier_photons_to_image,
            photon_exit_to_image,
            photon_origins_to_image,
            timepix_tot_to_image,
        )
        import analysis.spatial as spatial_module

        cls.intensifier_photons_to_image = staticmethod(intensifier_photons_to_image)
        cls.photon_exit_to_image = staticmethod(photon_exit_to_image)
        cls.photon_origins_to_image = staticmethod(photon_origins_to_image)
        cls.timepix_tot_to_image = staticmethod(timepix_tot_to_image)
        cls.spatial_module = spatial_module

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
                self.spatial_module,
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

    def test_timepix_tot_plot_accumulates_time_over_threshold_by_pixel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hdf5_path = Path(tmp_dir) / "timepix_hits.h5"
            self._write_timepix_hdf5(hdf5_path)

            fig, ax = self.timepix_tot_to_image(
                hdf5_path,
                show=False,
                log_scale=False,
            )

            image = ax.images[0].get_array()
            self.assertEqual(image.shape, (2, 2))
            self.assertAlmostEqual(float(image[0, 0]), 12.0)
            self.assertAlmostEqual(float(image[1, 1]), 3.0)
            self.assertEqual(ax.get_xlabel(), "x pixel")
            self.assertEqual(ax.get_ylabel(), "y pixel")
            self.plt.close(fig)
