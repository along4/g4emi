"""Unit tests for HDF5 schema constants."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


def _repo_root() -> Path:
    """Resolve repository root by searching parent directories."""

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src").is_dir() and (parent / "pixi.toml").is_file():
            return parent
    raise RuntimeError("Could not resolve repository root from test path.")


sys.path.insert(0, str(_repo_root()))


class Hdf5SchemaTests(unittest.TestCase):
    """Validate canonical dataset and field-name constants."""

    def test_intensifier_output_schema_constants_are_defined(self) -> None:
        from src.common.hdf5_schema import DATASET_INTENSIFIER_OUTPUT_EVENTS
        from src.common.hdf5_schema import INTENSIFIER_OUTPUT_FIELDS

        self.assertEqual(DATASET_INTENSIFIER_OUTPUT_EVENTS, "intensifier_output_events")
        self.assertEqual(
            INTENSIFIER_OUTPUT_FIELDS,
            (
                "source_photon_index",
                "gun_call_id",
                "primary_track_id",
                "secondary_track_id",
                "photon_track_id",
                "output_x_mm",
                "output_y_mm",
                "output_time_ns",
                "signal_amplitude_arb",
                "total_gain",
                "wavelength_nm",
            ),
        )

    def test_timepix_hit_schema_constants_are_defined(self) -> None:
        from src.common.hdf5_schema import DATASET_TIMEPIX_HITS
        from src.common.hdf5_schema import TIMEPIX_HIT_FIELDS

        self.assertEqual(DATASET_TIMEPIX_HITS, "timepix_hits")
        self.assertEqual(
            TIMEPIX_HIT_FIELDS,
            (
                "gun_call_id",
                "primary_track_id",
                "secondary_track_id",
                "x_pixel",
                "y_pixel",
                "time_of_arrival_ns",
                "time_over_threshold_ns",
                "contribution_count",
            ),
        )


if __name__ == "__main__":
    unittest.main()
