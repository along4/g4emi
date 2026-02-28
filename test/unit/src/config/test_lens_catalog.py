"""Unit tests for lens catalog IO and SimConfig lens hydration."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import textwrap
import unittest


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src").is_dir() and (parent / "pixi.toml").is_file():
            return parent
    raise RuntimeError("Could not resolve repository root from test path.")


sys.path.insert(0, str(_repo_root()))


class LensCatalogTests(unittest.TestCase):
    """Validate lens catalog loading and `catalogId` hydration workflow."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from src.config.ConfigIO import from_yaml
            from src.config.LensCatalogIO import load_lens
        except ModuleNotFoundError as exc:
            missing = (getattr(exc, "name", "") or "").lower()
            if missing in {"pydantic", "yaml"}:
                raise unittest.SkipTest(
                    f"Missing dependency for lens-catalog tests: {exc}. "
                    "Run in the project environment (for example: pixi run test-python)."
                ) from exc
            raise

        cls._from_yaml = staticmethod(from_yaml)
        cls._load_lens = staticmethod(load_lens)

    def test_load_lens_resolves_catalog_paths(self) -> None:
        """`load_lens` should resolve `.zmx`/`.smx` paths from catalog IDs."""

        loaded = self._load_lens("CanonEF50mmf1.0L")
        self.assertEqual(loaded.id, "CanonEF50mmf1.0L")
        self.assertTrue(loaded.zmx_path.exists())
        self.assertTrue(str(loaded.zmx_path).endswith("lenses/zmxFiles/CanonEF50mmf1.0L.zmx"))
        self.assertIsNotNone(loaded.smx_path)
        assert loaded.smx_path is not None
        self.assertTrue(loaded.smx_path.exists())
        self.assertTrue(str(loaded.smx_path).endswith("lenses/smxFiles/CanonEF50mmf1.0L.smx"))

    def test_from_yaml_hydrates_optical_lens_from_catalog_id(self) -> None:
        """`optical.lenses[*].catalogId` should backfill name/zmxFile/smxFile."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            yaml_path = tmp_path / "lens_catalog_hydration.yaml"
            yaml_path.write_text(
                textwrap.dedent(
                    """
                    scintillator:
                      catalogId: EJ200
                      position_mm:
                        x_mm: 0.0
                        y_mm: 0.0
                        z_mm: 0.0
                      dimension_mm:
                        x_mm: 100.0
                        y_mm: 100.0
                        z_mm: 20.0

                    source:
                      gps:
                        particle: neutron
                        position:
                          type: Plane
                          shape: Circle
                          centerMm:
                            x_mm: 0.0
                            y_mm: 0.0
                            z_mm: -100.0
                          radiusMm: 10.0
                        angular:
                          type: beam2d
                          rot1: {x: 1.0, y: 0.0, z: 0.0}
                          rot2: {x: 0.0, y: 1.0, z: 0.0}
                          direction: {x: 0.0, y: 0.0, z: 1.0}
                        energy:
                          type: Mono
                          monoMeV: 6.0

                    optical:
                      lenses:
                        - catalogId: CanonEF50mmf1.0L
                          primary: true
                      geometry:
                        entranceDiameter: 60.55
                        sensorMaxWidth: 36.0
                      sensitiveDetectorConfig:
                        position_mm:
                          x_mm: 0.0
                          y_mm: 0.0
                          z_mm: 210.05
                        shape: circle
                        diameterRule: min(entranceDiameter,sensorMaxWidth)

                    Metadata:
                      author: Unit Test
                      date: 2026-02-27
                      version: test
                      description: Validate lens catalog hydration.
                      RunEnvironment:
                        SimulationRunID: unit_lens_catalog_hydration
                        WorkingDirectory: data
                        MacroDirectory: macros
                        LogDirectory: logs
                        OutputInfo:
                          SimulatedPhotonsDirectory: simulatedPhotons
                          TransportedPhotonsDirectory: transportedPhotons
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            config = self._from_yaml(yaml_path)
            lens = config.optical.lenses[0]
            self.assertEqual(lens.catalog_id, "CanonEF50mmf1.0L")
            self.assertEqual(lens.name, "CanonEF50mmf1.0L")
            self.assertEqual(lens.zmx_file, "CanonEF50mmf1.0L.zmx")
            self.assertEqual(lens.smx_file, "CanonEF50mmf1.0L.smx")


if __name__ == "__main__":
    unittest.main()
