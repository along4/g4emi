"""Unit tests for event-level analysis helpers."""

from __future__ import annotations

from pathlib import Path
import tempfile

from test.unit.analysis._support import AnalysisDataBuilderMixin, AnalysisTestCase


class EventAnalysisTests(AnalysisDataBuilderMixin, AnalysisTestCase):
    """Validate event recoil-path plotting helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        from analysis.events import event_recoil_paths_to_image

        cls.event_recoil_paths_to_image = staticmethod(event_recoil_paths_to_image)

    def test_event_recoil_paths_plot_selected_event_in_requested_plane(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hdf5_path = Path(tmp_dir) / "photon_optical_interface_hits.h5"
            self._write_event_recoil_hdf5(hdf5_path)

            fig, ax = self.event_recoil_paths_to_image(
                hdf5_path,
                7,
                plane="xy",
                show=False,
            )

            self.assertEqual(ax.get_xlabel(), "x (mm)")
            self.assertEqual(ax.get_ylabel(), "y (mm)")
            self.assertIn("event 7", ax.get_title())
            self.assertEqual(len(ax.lines), 2)
            self.assertEqual(len(ax.collections), 2)
            legend = ax.get_legend()
            self.assertIsNotNone(legend)
            legend_labels = [text.get_text() for text in legend.get_texts()]
            self.assertEqual(
                legend_labels,
                ["proton #21 (photons=2)", "alpha #22 (photons=1)"],
            )
            self.plt.close(fig)

    def test_event_recoil_paths_ignores_nan_endpoints_when_setting_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hdf5_path = Path(tmp_dir) / "photon_optical_interface_hits.h5"
            self._write_event_recoil_hdf5(hdf5_path)

            fig, ax = self.event_recoil_paths_to_image(
                hdf5_path,
                9,
                plane="xy",
                show=False,
            )

            self.assertEqual(len(ax.lines), 0)
            self.assertEqual(len(ax.collections), 1)
            self.assertTrue(self.np.all(self.np.isfinite(self.np.asarray(ax.get_xlim()))))
            self.assertTrue(self.np.all(self.np.isfinite(self.np.asarray(ax.get_ylim()))))
            legend = ax.get_legend()
            self.assertIsNotNone(legend)
            legend_labels = [text.get_text() for text in legend.get_texts()]
            self.assertEqual(legend_labels, ["proton #41 (photons=2)"])
            self.plt.close(fig)
