"""Regression checks for simulation-side scintillation material setup."""

from __future__ import annotations

from pathlib import Path
import unittest


def _repo_root() -> Path:
    """Resolve repository root by searching parent directories."""

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (
            (parent / "pixi.toml").is_file()
            and (parent / "sim").is_dir()
            and (parent / "src").is_dir()
        ):
            return parent
    raise RuntimeError("Could not resolve repository root from test path.")


class DetectorConstructionSourceTests(unittest.TestCase):
    """Guard against dropping configured scintillation components in Geant4 setup."""

    def test_detector_construction_sets_all_scintillation_components(self) -> None:
        """Detector construction should forward all three timing components."""

        source = (_repo_root() / "sim" / "src" / "DetectorConstruction.cc").read_text(
            encoding="utf-8"
        )

        required_tokens = [
            '"SCINTILLATIONCOMPONENT1"',
            '"SCINTILLATIONCOMPONENT2"',
            '"SCINTILLATIONCOMPONENT3"',
            '"SCINTILLATIONTIMECONSTANT1"',
            '"SCINTILLATIONTIMECONSTANT2"',
            '"SCINTILLATIONTIMECONSTANT3"',
            '"SCINTILLATIONYIELD1"',
            '"SCINTILLATIONYIELD2"',
            '"SCINTILLATIONYIELD3"',
            "config->GetScintTimeConstant(componentIndex)",
            "config->GetScintYieldFraction(componentIndex)",
        ]

        for token in required_tokens:
            with self.subTest(token=token):
                self.assertIn(token, source)


if __name__ == "__main__":
    unittest.main()
