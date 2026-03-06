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
                intensifier_photons_to_image,
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
        cls.intensifier_photons_to_image = staticmethod(intensifier_photons_to_image)
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


if __name__ == "__main__":
    unittest.main()
