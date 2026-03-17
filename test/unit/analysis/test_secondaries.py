"""Unit tests for secondary-track analysis helpers."""

from __future__ import annotations

from pathlib import Path
import tempfile

from test.unit.analysis._support import AnalysisDataBuilderMixin, AnalysisTestCase


class SecondaryAnalysisTests(AnalysisDataBuilderMixin, AnalysisTestCase):
    """Validate secondary-track grouping and overlay helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        from analysis.secondaries import (
            secondary_track_lengths_by_species_mm,
            secondary_track_lengths_overlay_to_histogram,
        )

        cls.secondary_track_lengths_by_species_mm = staticmethod(
            secondary_track_lengths_by_species_mm
        )
        cls.secondary_track_lengths_overlay_to_histogram = staticmethod(
            secondary_track_lengths_overlay_to_histogram
        )

    def test_secondary_track_lengths_are_grouped_by_species(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hdf5_path = Path(tmp_dir) / "photon_optical_interface_hits.h5"
            self._write_secondaries_hdf5(hdf5_path)

            grouped = self.secondary_track_lengths_by_species_mm(hdf5_path)

            self.assertEqual(sorted(grouped.keys()), ["alpha", "proton"])
            self.assertTrue(
                self.np.allclose(grouped["proton"], self.np.array([5.0, 6.0]))
            )
            self.assertTrue(self.np.allclose(grouped["alpha"], self.np.array([10.0])))

    def test_secondary_track_length_overlay_uses_requested_alpha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hdf5_path = Path(tmp_dir) / "photon_optical_interface_hits.h5"
            self._write_secondaries_hdf5(hdf5_path)

            fig, ax = self.secondary_track_lengths_overlay_to_histogram(
                hdf5_path,
                bins=[0.0, 4.0, 8.0, 12.0],
                alpha=0.35,
                x_max=8.0,
                show=False,
            )

            self.assertEqual(ax.get_xlabel(), "track length (mm)")
            self.assertEqual(ax.get_ylabel(), "counts")
            self.assertIn("Track Lengths", ax.get_title())
            self.assertEqual(ax.get_yscale(), "log")
            self.assertAlmostEqual(float(ax.get_xlim()[0]), 0.0)
            self.assertAlmostEqual(float(ax.get_xlim()[1]), 8.0)
            self.assertEqual(len(ax.patches), 2)
            self.assertTrue(
                all(
                    abs(float(patch.get_alpha()) - 0.35) < 1.0e-9
                    for patch in ax.patches
                )
            )
            legend = ax.get_legend()
            self.assertIsNotNone(legend)
            legend_labels = [text.get_text() for text in legend.get_texts()]
            self.assertEqual(legend_labels, ["alpha (n=1)", "proton (n=2)"])
            self.plt.close(fig)

    def test_secondary_track_length_overlay_accepts_precomputed_grouped_lengths(
        self,
    ) -> None:
        grouped_lengths = {
            "alpha": self.np.array([2.0, 3.0], dtype=float),
            "proton": self.np.array([1.0, 4.0, 5.0], dtype=float),
        }

        fig, ax = self.secondary_track_lengths_overlay_to_histogram(
            grouped_lengths_mm=grouped_lengths,
            bins=[0.0, 2.0, 4.0, 6.0],
            alpha=0.4,
            log_scale=False,
            show=False,
        )

        legend = ax.get_legend()
        self.assertIsNotNone(legend)
        legend_labels = [text.get_text() for text in legend.get_texts()]
        self.assertEqual(legend_labels, ["alpha (n=2)", "proton (n=3)"])
        self.assertEqual(ax.get_yscale(), "linear")
        self.plt.close(fig)
