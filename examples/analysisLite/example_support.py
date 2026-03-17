"""Shared support helpers for analysisLite example scripts."""

from __future__ import annotations

from pathlib import Path
import sys


def ensure_repo_root_on_path() -> Path:
    """Add the repository root to ``sys.path`` when examples run directly."""

    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.append(repo_root_str)
    return repo_root


def default_output_dir_from_input(hdf5_path: Path) -> Path:
    """Infer the default analyzer output directory from an input HDF5 path."""

    stage_dir_names = {"simulatedPhotons", "transportedPhotons"}
    if hdf5_path.parent.name in stage_dir_names:
        return hdf5_path.parent.parent / "plots"
    return hdf5_path.parent / "plots"


def infer_transport_hdf5_path(sim_hdf5_path: Path) -> Path | None:
    """Infer the sibling transport HDF5 path for a simulated-photons file."""

    if sim_hdf5_path.parent.name != "simulatedPhotons":
        return None
    run_root = sim_hdf5_path.parent.parent
    suffix = sim_hdf5_path.stem.removeprefix("photon_optical_interface_hits")
    candidate = run_root / "transportedPhotons" / f"photons_intensifier_hits{suffix}.h5"
    return candidate if candidate.exists() else None
