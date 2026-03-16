"""Generate macros from one YAML config and run sequential sub-runs."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure repository root is importable when this file is run directly.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from src.config.ConfigIO import from_yaml  # noqa: E402
from src.config.SimConfig import SimConfig, SimulationConfig  # noqa: E402
from src.runner.runSimulation import run_simulation  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Load one SimConfig YAML, set `SubRunNumber` in memory for each "
            "batch slot, generate a macro, and run g4emi sequentially."
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
        "--sub-run-count",
        type=int,
        default=2,
        help="Number of sequential sub-runs to execute (default: 2).",
    )
    parser.add_argument(
        "--first-sub-run-number",
        type=int,
        default=0,
        help="Starting sub-run number (default: 0).",
    )
    parser.add_argument(
        "--beam-on",
        type=int,
        default=None,
        help="Optional override for simulation numberOfParticles.",
    )
    parser.add_argument(
        "--g4emi-binary",
        type=str,
        default=None,
        help="Optional override for `runner.binary` from the YAML config.",
    )
    parser.add_argument(
        "--show-progress",
        action="store_true",
        help="Enable the Python-side terminal progress bar for each batch sub-run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate per-sub-run macros and print planned paths without launching g4emi.",
    )
    return parser


def _base_config_from_args(args: argparse.Namespace) -> SimConfig:
    """Load YAML and apply one-time CLI overrides."""

    config = from_yaml(args.yaml_path.expanduser().resolve())
    if args.beam_on is not None:
        if config.simulation is None:
            config.simulation = SimulationConfig(number_of_particles=args.beam_on)
        else:
            config.simulation.number_of_particles = args.beam_on
    if args.g4emi_binary is not None:
        config.runner.binary = args.g4emi_binary
    return config


def _config_for_sub_run(
    base_config: SimConfig,
    *,
    sub_run_number: int,
    show_progress: bool,
) -> SimConfig:
    """Return an isolated config copy for one batch sub-run."""

    config = base_config.model_copy(deep=True)
    config.metadata.run_environment.sub_run_number = sub_run_number
    # Batch mode defaults the Python-side progress bar to off unless requested.
    config.runner.show_progress = show_progress
    return config


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.sub_run_count <= 0:
        raise ValueError("--sub-run-count must be > 0.")
    if args.first_sub_run_number < 0:
        raise ValueError("--first-sub-run-number must be >= 0.")

    base_config = _base_config_from_args(args)

    for offset in range(args.sub_run_count):
        sub_run_number = args.first_sub_run_number + offset
        config = _config_for_sub_run(
            base_config,
            sub_run_number=sub_run_number,
            show_progress=args.show_progress,
        )
        run_simulation(config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
