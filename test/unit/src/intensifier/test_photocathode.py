"""Unit tests for the intensifier photocathode stage."""

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


class PhotocathodeStageTests(unittest.TestCase):
    """Validate QE interpolation and photoelectron generation."""

    @classmethod
    def setUpClass(cls) -> None:
        from src.intensifier.models import PhotocathodeParams
        from src.intensifier.models import TransportedPhotonBatch
        from src.intensifier.photocathode import convert_photons_to_photoelectrons
        from src.intensifier.photocathode import interpolate_qe

        cls.PhotocathodeParams = PhotocathodeParams
        cls.TransportedPhotonBatch = TransportedPhotonBatch
        cls.convert_photons_to_photoelectrons = staticmethod(
            convert_photons_to_photoelectrons
        )
        cls.interpolate_qe = staticmethod(interpolate_qe)

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

    def test_interpolate_qe_returns_zero_outside_range(self) -> None:
        params = self.PhotocathodeParams(
            qe_wavelength_nm=np.array([400.0, 500.0, 600.0], dtype=np.float64),
            qe_values=np.array([0.1, 0.4, 0.2], dtype=np.float64),
            collection_efficiency=1.0,
            tts_sigma_ns=0.0,
        )

        result = self.interpolate_qe(
            np.array([350.0, 400.0, 450.0, 650.0], dtype=np.float64),
            params,
        )

        np.testing.assert_allclose(
            result,
            np.array([0.0, 0.1, 0.25, 0.0], dtype=np.float64),
        )

    def test_convert_photons_to_photoelectrons_rejects_all_when_qe_is_zero(self) -> None:
        params = self.PhotocathodeParams(
            qe_wavelength_nm=np.array([400.0, 500.0], dtype=np.float64),
            qe_values=np.array([0.0, 0.0], dtype=np.float64),
            collection_efficiency=1.0,
            tts_sigma_ns=0.0,
        )

        result = self.convert_photons_to_photoelectrons(
            self._photons(),
            params,
            rng=np.random.default_rng(123),
        )

        self.assertEqual(len(result), 0)

    def test_convert_photons_to_photoelectrons_keeps_all_when_detection_probability_is_one(self) -> None:
        photons = self._photons()
        params = self.PhotocathodeParams(
            qe_wavelength_nm=np.array([350.0, 700.0], dtype=np.float64),
            qe_values=np.array([1.0, 1.0], dtype=np.float64),
            collection_efficiency=1.0,
            tts_sigma_ns=0.0,
        )

        result = self.convert_photons_to_photoelectrons(
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
        np.testing.assert_allclose(result.x_pc_mm, photons.x_mm)
        np.testing.assert_allclose(result.y_pc_mm, photons.y_mm)
        np.testing.assert_allclose(result.time_pc_ns, photons.time_ns)
        np.testing.assert_allclose(result.wavelength_nm, photons.wavelength_nm)

    def test_convert_photons_to_photoelectrons_adds_timing_jitter_when_enabled(self) -> None:
        photons = self._photons()
        params = self.PhotocathodeParams(
            qe_wavelength_nm=np.array([350.0, 700.0], dtype=np.float64),
            qe_values=np.array([1.0, 1.0], dtype=np.float64),
            collection_efficiency=1.0,
            tts_sigma_ns=0.5,
        )

        result = self.convert_photons_to_photoelectrons(
            photons,
            params,
            rng=np.random.default_rng(123),
        )

        self.assertEqual(len(result), len(photons))
        self.assertFalse(np.allclose(result.time_pc_ns, photons.time_ns))


if __name__ == "__main__":
    unittest.main()
