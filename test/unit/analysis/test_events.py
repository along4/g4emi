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
        from analysis.events import (
            event_recoil_paths_to_image,
            gun_call_ids_with_secondary_species,
            random_gun_call_id,
        )

        cls.event_recoil_paths_to_image = staticmethod(event_recoil_paths_to_image)
        cls.gun_call_ids_with_secondary_species = staticmethod(
            gun_call_ids_with_secondary_species
        )
        cls.random_gun_call_id = staticmethod(random_gun_call_id)

    def test_gun_call_ids_with_secondary_species_filters_to_matching_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hdf5_path = Path(tmp_dir) / "photon_optical_interface_hits.h5"
            self._write_event_recoil_hdf5(hdf5_path)

            proton_ids = self.gun_call_ids_with_secondary_species(
                hdf5_path,
                secondary_species="proton",
            )
            alpha_ids = self.gun_call_ids_with_secondary_species(
                hdf5_path,
                secondary_species="alpha",
            )

            self.assertEqual(proton_ids.tolist(), [7, 8, 9])
            self.assertEqual(alpha_ids.tolist(), [7])

    def test_gun_call_ids_with_secondary_species_accepts_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hdf5_path = Path(tmp_dir) / "photon_optical_interface_hits.h5"
            self._write_event_recoil_hdf5(hdf5_path)

            proton_ids = self.gun_call_ids_with_secondary_species(
                hdf5_path,
                secondary_species="p",
            )
            proton_alias_ids = self.gun_call_ids_with_secondary_species(
                hdf5_path,
                secondary_species="proton",
            )

            self.assertEqual(proton_ids.tolist(), proton_alias_ids.tolist())

    def test_random_gun_call_id_is_reproducible_with_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hdf5_path = Path(tmp_dir) / "photon_optical_interface_hits.h5"
            self._write_event_recoil_hdf5(hdf5_path)

            first = self.random_gun_call_id(
                hdf5_path,
                secondary_species="proton",
                seed=1234,
            )
            second = self.random_gun_call_id(
                hdf5_path,
                secondary_species="proton",
                seed=1234,
            )

            self.assertEqual(first, second)
            self.assertIn(first, {7, 8, 9})

    def test_event_recoil_paths_plot_selected_event_in_requested_plane(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hdf5_path = Path(tmp_dir) / "photon_optical_interface_hits.h5"
            transport_hdf5_path = Path(tmp_dir) / "photons_intensifier_hits.h5"
            self._write_event_recoil_hdf5(hdf5_path)
            self._write_event_transport_hdf5(transport_hdf5_path)

            fig, ax = self.event_recoil_paths_to_image(
                hdf5_path,
                7,
                plane="xy",
                transport_hdf5_path=transport_hdf5_path,
                show=False,
            )

            self.assertEqual(ax.get_xlabel(), "x (mm)")
            self.assertEqual(ax.get_ylabel(), "y (mm)")
            self.assertIn("event 7", ax.get_title())
            self.assertEqual(len(ax.lines), 2)
            self.assertEqual(len(ax.collections), 9)
            legend = ax.get_legend()
            self.assertIsNotNone(legend)
            legend_labels = [text.get_text() for text in legend.get_texts()]
            self.assertEqual(
                legend_labels,
                [
                    "Neutron hit",
                    "proton #21, 4.250 MeV, enter-lens=2",
                    "alpha #22, 1.500 MeV, enter-lens=1",
                    "Photon origins (missed intensifier)",
                    "Photon exits (missed intensifier)",
                    "Photon origins (reached intensifier)",
                    "Photon exits (reached intensifier)",
                ],
            )
            hover_texts = [
                getattr(artist, "_hover_text", None)
                for artist in [*ax.lines, *ax.collections]
                if getattr(artist, "_hover_text", None) is not None
            ]
            self.assertTrue(any("Neutron hit" in text for text in hover_texts))
            self.assertTrue(
                any(
                    "proton #21" in text
                    and "4.250 MeV" in text
                    and "enter-lens photons=2" in text
                    for text in hover_texts
                )
            )
            self.assertTrue(any("Photon exits" in text for text in hover_texts))
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
            self.assertEqual(len(ax.collections), 3)
            self.assertTrue(self.np.all(self.np.isfinite(self.np.asarray(ax.get_xlim()))))
            self.assertTrue(self.np.all(self.np.isfinite(self.np.asarray(ax.get_ylim()))))
            legend = ax.get_legend()
            self.assertIsNotNone(legend)
            legend_labels = [text.get_text() for text in legend.get_texts()]
            self.assertEqual(legend_labels, ["Neutron hit", "Photon origins", "Photon exits"])
            self.plt.close(fig)
