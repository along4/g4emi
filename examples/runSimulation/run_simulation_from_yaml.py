"""Generate macro from YAML and run g4emi in one step."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure repository root is importable when this file is run directly.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from src.config.ConfigIO import from_yaml  # noqa: E402
from src.config.SimConfig import SimulationConfig  # noqa: E402
from src.runner.runSimulation import run_simulation  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Load SimConfig YAML, generate macro, and run g4emi with that macro."
        )
    )
    parser.add_argument(
        "yaml_path",
        nargs="?",
        type=Path,
        default=REPO_ROOT / "examples" / "yamlFiles" / "CanonEF50mmf1p0L_example.yaml",
        help="SimConfig YAML path (default: Canon example under examples/yamlFiles).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate macro and print run command without launching g4emi.",
    )
    parser.add_argument(
        "--beam-on",
        type=int,
        default=None,
        help="Optional override for simulation numberOfParticles.",
    )
    return parser

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    config = from_yaml(args.yaml_path.expanduser().resolve())
    if args.beam_on is not None:
        if config.simulation is None:
            config.simulation = SimulationConfig(number_of_particles=args.beam_on)
        else:
            config.simulation.number_of_particles = args.beam_on
    run_simulation(config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
