"""Unit tests for scintillator catalog loading."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import textwrap
import unittest


def _repo_root() -> Path:
    """Resolve repository root by searching parent directories."""

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src").is_dir() and (parent / "pixi.toml").is_file():
            return parent
    raise RuntimeError("Could not resolve repository root from test path.")


sys.path.insert(0, str(_repo_root()))


class ScintillatorCatalogTests(unittest.TestCase):
    """Validate scintillator catalog index/material/curve loading."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from src.config.ScintillatorCatalogIO import (
                available_scintillators,
                load_scintillator,
                load_scintillator_definition,
            )
        except ModuleNotFoundError as exc:
            missing_name = (getattr(exc, "name", "") or "").lower()
            if "pydantic" in missing_name or "yaml" in missing_name:
                raise unittest.SkipTest(
                    f"Missing dependency for catalog tests: {exc}. "
                    "Run in the project environment (for example: pixi run test-python)."
                ) from exc
            raise

        cls._available_scintillators = staticmethod(available_scintillators)
        cls._load_scintillator = staticmethod(load_scintillator)
        cls._load_scintillator_definition = staticmethod(load_scintillator_definition)

    def test_default_catalog_contains_ej200(self) -> None:
        """Catalog index should expose the default EJ200 entry."""

        materials = self._available_scintillators()
        self.assertIn("EJ200", materials)
        self.assertIn("EJ-426", materials)
        self.assertIn("EJ-276D", materials)
        self.assertIn("EJ-276G", materials)
        self.assertIn("CsI-Na", materials)
        self.assertIn("CsI-Tl", materials)
        self.assertIn("NaI-Tl", materials)

    def test_load_default_scintillator(self) -> None:
        """Loading without explicit id should return catalog default."""

        loaded = self._load_scintillator()
        self.assertEqual(loaded.material.id, "EJ200")
        self.assertEqual(loaded.material.composition.atoms["C"], 9)
        self.assertEqual(loaded.material.composition.atoms["H"], 10)
        self.assertEqual(len(loaded.r_index.energy), 5)
        self.assertEqual(loaded.r_index.energy[0], 2.0)
        self.assertEqual(loaded.r_index.value[0], 1.58)
        self.assertEqual(
            [c.time_constant.value for c in loaded.material.optical.constants.time_components],
            [2.1, 0.0, 0.0],
        )
        self.assertEqual(
            [c.yield_fraction for c in loaded.material.optical.constants.time_components],
            [1.0, 0.0, 0.0],
        )

    def test_load_material_definition(self) -> None:
        """Material-only loader should parse metadata/constants."""

        material = self._load_scintillator_definition("EJ200")
        self.assertEqual(material.name, "Eljen EJ-200")
        self.assertEqual(material.optical.constants.scint_yield.value, 10000.0)
        self.assertEqual(
            material.optical.constants.time_components[0].time_constant.unit, "ns"
        )

    def test_time_components_schema_requires_exactly_three(self) -> None:
        """Catalog materials should expose exactly three time components."""

        for material_id in self._available_scintillators():
            material = self._load_scintillator_definition(material_id)
            self.assertEqual(
                len(material.optical.constants.time_components),
                3,
                msg=f"{material_id} did not define exactly three time components.",
            )

    def test_time_components_schema_rejects_non_three_components(self) -> None:
        """Schema should reject materials that do not define exactly three components."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "materials").mkdir(parents=True, exist_ok=True)

            (root / "catalog.yaml").write_text(
                textwrap.dedent(
                    """
                    version: 1
                    default: TEST
                    materials:
                      TEST: materials/TEST.yaml
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            (root / "materials" / "TEST.yaml").write_text(
                textwrap.dedent(
                    """
                    id: TEST
                    name: Test Material
                    composition:
                      density: {value: 1.0, unit: g/cm3}
                      atoms: {C: 1}
                    optical:
                      curves:
                        rIndex: {path: curves/TEST/rindex.csv, xUnit: eV, yUnit: unitless}
                        absLength: {path: curves/TEST/abs.csv, xUnit: eV, yUnit: cm}
                        scintSpectrum: {path: curves/TEST/scint.csv, xUnit: eV, yUnit: unitless}
                      constants:
                        scintYield: {value: 1000.0, unit: 1/MeV}
                        resolutionScale: 1.0
                        timeComponents:
                          - timeConstant: {value: 1.0, unit: ns}
                            yieldFraction: 1.0
                          - timeConstant: {value: 0.0, unit: ns}
                            yieldFraction: 0.0
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                self._load_scintillator_definition("TEST", catalog_path=root / "catalog.yaml")

    def test_time_components_schema_rejects_fraction_sum_not_one(self) -> None:
        """Schema should reject three components when yield fractions do not sum to ~1.0."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "materials").mkdir(parents=True, exist_ok=True)

            (root / "catalog.yaml").write_text(
                textwrap.dedent(
                    """
                    version: 1
                    default: TEST
                    materials:
                      TEST: materials/TEST.yaml
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            (root / "materials" / "TEST.yaml").write_text(
                textwrap.dedent(
                    """
                    id: TEST
                    name: Test Material
                    composition:
                      density: {value: 1.0, unit: g/cm3}
                      atoms: {C: 1}
                    optical:
                      curves:
                        rIndex: {path: curves/TEST/rindex.csv, xUnit: eV, yUnit: unitless}
                        absLength: {path: curves/TEST/abs.csv, xUnit: eV, yUnit: cm}
                        scintSpectrum: {path: curves/TEST/scint.csv, xUnit: eV, yUnit: unitless}
                      constants:
                        scintYield: {value: 1000.0, unit: 1/MeV}
                        resolutionScale: 1.0
                        timeComponents:
                          - timeConstant: {value: 1.0, unit: ns}
                            yieldFraction: 0.8
                          - timeConstant: {value: 2.0, unit: ns}
                            yieldFraction: 0.1
                          - timeConstant: {value: 3.0, unit: ns}
                            yieldFraction: 0.05
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                self._load_scintillator_definition("TEST", catalog_path=root / "catalog.yaml")

    def test_load_ej276_variants(self) -> None:
        """EJ-276D/G entries should resolve with expected SSLG4 constants."""

        ej276d = self._load_scintillator("EJ-276D")
        self.assertEqual(ej276d.material.name, "EJ-276D")
        self.assertEqual(ej276d.material.optical.constants.scint_yield.value, 8600.0)
        self.assertEqual(
            ej276d.material.optical.constants.time_components[0].time_constant.value,
            13.0,
        )
        self.assertEqual(
            ej276d.material.optical.constants.time_components[1].time_constant.value,
            59.0,
        )
        self.assertEqual(
            ej276d.material.optical.constants.time_components[2].time_constant.value,
            460.0,
        )
        self.assertEqual(len(ej276d.r_index.energy), 5)

        ej276g = self._load_scintillator("EJ-276G")
        self.assertEqual(ej276g.material.name, "EJ-276G")
        self.assertEqual(ej276g.material.optical.constants.scint_yield.value, 8000.0)
        self.assertEqual(
            ej276g.material.optical.constants.time_components[0].time_constant.value,
            13.0,
        )
        self.assertEqual(
            ej276g.material.optical.constants.time_components[1].time_constant.value,
            35.0,
        )
        self.assertEqual(
            ej276g.material.optical.constants.time_components[2].time_constant.value,
            270.0,
        )
        self.assertEqual(len(ej276g.r_index.energy), 5)

    def test_load_ej426(self) -> None:
        """EJ-426 entry should load SSLG4-derived constants and curve grid."""

        ej426 = self._load_scintillator("EJ-426")
        self.assertEqual(ej426.material.name, "EJ-426")
        self.assertEqual(ej426.material.composition.density.value, 2.42)
        self.assertEqual(ej426.material.optical.constants.scint_yield.value, 40000.0)
        self.assertEqual(
            ej426.material.optical.constants.time_components[0].time_constant.value,
            200.0,
        )
        self.assertEqual(len(ej426.r_index.energy), 79)

    def test_load_csi_and_nai_variants(self) -> None:
        """CsI/NaI entries should load SSLG4-derived iodide constants."""

        csi_na = self._load_scintillator("CsI-Na")
        self.assertEqual(csi_na.material.name, "CsI(Na)")
        self.assertEqual(csi_na.material.optical.constants.scint_yield.value, 41000.0)
        self.assertEqual(
            csi_na.material.optical.constants.time_components[0].time_constant.value,
            630.0,
        )
        self.assertEqual(len(csi_na.r_index.energy), 77)

        csi_tl = self._load_scintillator("CsI-Tl")
        self.assertEqual(csi_tl.material.name, "CsI(Tl)")
        self.assertEqual(csi_tl.material.optical.constants.scint_yield.value, 54000.0)
        self.assertEqual(
            csi_tl.material.optical.constants.time_components[0].time_constant.value,
            1000.0,
        )
        self.assertEqual(len(csi_tl.r_index.energy), 77)

        nai_tl = self._load_scintillator("NaI-Tl")
        self.assertEqual(nai_tl.material.name, "NaI(Tl)")
        self.assertEqual(nai_tl.material.optical.constants.scint_yield.value, 41000.0)
        self.assertEqual(
            nai_tl.material.optical.constants.time_components[0].time_constant.value,
            630.0,
        )
        self.assertEqual(len(nai_tl.r_index.energy), 77)

    def test_mismatched_curve_energy_grid_raises(self) -> None:
        """Curve files with different energy grids should be rejected."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "materials").mkdir(parents=True, exist_ok=True)
            (root / "curves" / "TEST").mkdir(parents=True, exist_ok=True)

            (root / "catalog.yaml").write_text(
                textwrap.dedent(
                    """
                    version: 1
                    default: TEST
                    materials:
                      TEST: materials/TEST.yaml
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            (root / "materials" / "TEST.yaml").write_text(
                textwrap.dedent(
                    """
                    id: TEST
                    name: Test Material
                    composition:
                      density: {value: 1.0, unit: g/cm3}
                      atoms: {C: 1}
                    optical:
                      curves:
                        rIndex: {path: curves/TEST/rindex.csv, xUnit: eV, yUnit: unitless}
                        absLength: {path: curves/TEST/abs.csv, xUnit: eV, yUnit: cm}
                        scintSpectrum: {path: curves/TEST/scint.csv, xUnit: eV, yUnit: unitless}
                      constants:
                        scintYield: {value: 1000.0, unit: 1/MeV}
                        resolutionScale: 1.0
                        timeComponents:
                          - timeConstant: {value: 1.0, unit: ns}
                            yieldFraction: 1.0
                          - timeConstant: {value: 0.0, unit: ns}
                            yieldFraction: 0.0
                          - timeConstant: {value: 0.0, unit: ns}
                            yieldFraction: 0.0
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            (root / "curves" / "TEST" / "rindex.csv").write_text(
                "energy_eV,value\n2.0,1.5\n2.5,1.5\n",
                encoding="utf-8",
            )
            (root / "curves" / "TEST" / "abs.csv").write_text(
                "energy_eV,value\n2.0,10.0\n2.5,10.0\n",
                encoding="utf-8",
            )
            # Intentionally mismatched second energy node.
            (root / "curves" / "TEST" / "scint.csv").write_text(
                "energy_eV,value\n2.0,0.2\n2.6,0.4\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                self._load_scintillator(catalog_path=root / "catalog.yaml")


if __name__ == "__main__":
    unittest.main()
