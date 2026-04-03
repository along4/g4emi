"""Minimal example for lightweight timing analysis from simulation HDF5."""

from __future__ import annotations

import argparse
from pathlib import Path

from matplotlib import pyplot as plt
import numpy as np

from example_support import default_output_dir_from_input, ensure_repo_root_on_path  # noqa: E402

ensure_repo_root_on_path()
from analysis.timing import (  # noqa: E402
    ScintillationDecayComponent,
    decay_model_bin_counts,
    fit_photon_creation_delay_histogram,
    photon_creation_delays_ns,
    photon_creation_delay_to_histogram,
)


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for timing-analysis input/output paths."""

    parser = argparse.ArgumentParser(
        description="Generate lightweight timing-analysis plots from a g4emi HDF5 file."
    )
    parser.add_argument(
        "hdf5_path",
        type=Path,
        help="Path to input HDF5 file (e.g. data/.../photon_optical_interface_hits_0000.h5).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory for output PNGs "
            "(default: <run_root>/plots when inferable, else <input_dir>/plots)."
        ),
    )
    parser.add_argument(
        "--bins",
        type=int,
        default=256,
        help="Number of histogram bins for the timing plot (default: 256).",
    )
    parser.add_argument(
        "--fit",
        action="store_true",
        help="Fit a 3-component exponential model to the timing histogram.",
    )
    parser.add_argument(
        "--sim-config-yaml",
        type=Path,
        default=None,
        help=(
            "Optional SimConfig YAML used to load the configured 3-component "
            "decay model for overlay and fit initialization."
        ),
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display the plot interactively instead of writing a PNG.",
    )
    return parser.parse_args()


def _load_configured_decay_components(
    sim_config_yaml_path: Path,
) -> tuple[str, tuple[ScintillationDecayComponent, ...]]:
    """Load the active configured scintillation decay components from SimConfig."""

    try:
        from src.config.ConfigIO import from_yaml
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Could not import `src.config.ConfigIO.from_yaml` required for "
            "SimConfig-based timing overlays and fit initialization. Run in the "
            "project environment (for example: `pixi run python "
            "examples/analysisLite/hdf5_timing_analyzer_example.py ...`)."
        ) from exc

    config = from_yaml(sim_config_yaml_path)
    profile_name, resolved_components = (
        config.scintillator.properties.time_components.resolve_for_particle(
            config.source.gps.particle
        )
    )
    return (
        profile_name,
        tuple(
            ScintillationDecayComponent(
                time_constant_ns=float(component.time_constant),
                yield_fraction=float(component.yield_fraction),
            )
            for component in resolved_components
        ),
    )


def _format_components(
    components: tuple[ScintillationDecayComponent, ...],
) -> list[str]:
    """Format decay-component summaries for terminal output."""

    lines = []
    for index, component in enumerate(components, start=1):
        lines.append(
            "  "
            f"{index}. tau={component.time_constant_ns:.3f} ns, "
            f"yield={component.yield_fraction:.4f}"
        )
    return lines


def _plot_component_summary(
    ax,
    *,
    configured_profile_name: str | None,
    configured_components: tuple[ScintillationDecayComponent, ...] | None,
    fitted_components: tuple[ScintillationDecayComponent, ...] | None,
    fit_rmse_counts: float | None,
) -> None:
    """Render configured/fitted timing-component values onto the plot."""

    lines: list[str] = []
    if configured_components is not None:
        profile_suffix = (
            f" ({configured_profile_name})" if configured_profile_name is not None else ""
        )
        lines.append(f"Configured{profile_suffix}:")
        for index, component in enumerate(configured_components, start=1):
            lines.append(
                f"  C{index}: {component.time_constant_ns:.3f} ns, {component.yield_fraction:.4f}"
            )
    if fitted_components is not None:
        if lines:
            lines.append("")
        lines.append("Fitted:")
        for index, component in enumerate(fitted_components, start=1):
            lines.append(
                f"  F{index}: {component.time_constant_ns:.3f} ns, {component.yield_fraction:.4f}"
            )
        if fit_rmse_counts is not None:
            lines.append(f"  RMSE: {fit_rmse_counts:.3f}")
    if not lines:
        return

    ax.text(
        0.98,
        0.98,
        "\n".join(lines),
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=8,
        family="monospace",
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": "white",
            "alpha": 0.85,
            "edgecolor": "#666666",
        },
    )


def main() -> None:
    """Generate photon creation-delay timing plots from a simulation HDF5 file."""

    args = _parse_args()
    hdf5_path = args.hdf5_path.expanduser().resolve()
    if not hdf5_path.exists():
        raise FileNotFoundError(f"Input HDF5 file not found: {hdf5_path}")
    if args.bins <= 0:
        raise ValueError("--bins must be > 0.")

    output_dir = None
    if not args.show:
        output_dir = (
            args.output_dir.expanduser().resolve()
            if args.output_dir is not None
            else default_output_dir_from_input(hdf5_path).resolve()
        )
        output_dir.mkdir(parents=True, exist_ok=True)

    creation_delay_png = (
        None if output_dir is None else output_dir / "photon_creation_delay.png"
    )
    sim_config_yaml_path = (
        args.sim_config_yaml.expanduser().resolve()
        if args.sim_config_yaml is not None
        else None
    )
    if sim_config_yaml_path is not None and not sim_config_yaml_path.exists():
        raise FileNotFoundError(f"SimConfig YAML not found: {sim_config_yaml_path}")

    configured_profile_name = None
    configured_components = None
    if sim_config_yaml_path is not None:
        configured_profile_name, configured_components = _load_configured_decay_components(
            sim_config_yaml_path
        )

    fit_result = None
    if args.fit:
        fit_result = fit_photon_creation_delay_histogram(
            hdf5_path,
            bins=args.bins,
            initial_components=configured_components,
        )

    fig, ax = photon_creation_delay_to_histogram(
        hdf5_path,
        bins=args.bins,
        output_path=None,
    )
    observed_bin_edges = None
    observed_total_count = None
    if fit_result is not None:
        observed_bin_edges = fit_result.bin_edges_ns
        observed_total_count = float(np.sum(fit_result.observed_counts))
    if configured_components is not None:
        if observed_bin_edges is None:
            delays_ns = photon_creation_delays_ns(hdf5_path)
            observed_counts, observed_bin_edges = np.histogram(delays_ns, bins=args.bins)
            observed_total_count = float(np.sum(observed_counts))
        assert observed_total_count is not None
        configured_counts = decay_model_bin_counts(
            observed_bin_edges,
            total_count=observed_total_count,
            components=configured_components,
        )
        configured_centers = 0.5 * (observed_bin_edges[:-1] + observed_bin_edges[1:])
        ax.plot(
            configured_centers,
            configured_counts,
            color="#444444",
            linestyle="--",
            linewidth=1.5,
            label=f"Configured model ({configured_profile_name})",
        )
    if fit_result is not None:
        fitted_centers = 0.5 * (
            fit_result.bin_edges_ns[:-1] + fit_result.bin_edges_ns[1:]
        )
        ax.plot(
            fitted_centers,
            fit_result.fitted_counts,
            color="#c73e1d",
            linewidth=1.8,
            label="3-component fit",
        )
        ax.legend()
    elif configured_components is not None:
        ax.legend()

    _plot_component_summary(
        ax,
        configured_profile_name=configured_profile_name,
        configured_components=configured_components,
        fitted_components=(fit_result.components if fit_result is not None else None),
        fit_rmse_counts=(fit_result.rmse_counts if fit_result is not None else None),
    )

    if creation_delay_png is not None:
        fig.savefig(creation_delay_png, dpi=150)

    print(f"Input HDF5: {hdf5_path}")
    if sim_config_yaml_path is not None:
        print(f"SimConfig YAML: {sim_config_yaml_path}")
        print(f"Configured profile: {configured_profile_name}")
        print("Configured components:")
        for line in _format_components(configured_components):
            print(line)
    if fit_result is not None:
        print("Fitted components:")
        for line in _format_components(fit_result.components):
            print(line)
        print(f"Fit RMSE (counts/bin): {fit_result.rmse_counts:.3f}")
    if args.show:
        print("Displaying plot interactively.")
        plt.show()
        return

    print("Wrote images:")
    print(f"  - {creation_delay_png}")


if __name__ == "__main__":
    main()
