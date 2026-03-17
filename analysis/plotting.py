"""Shared matplotlib rendering helpers for analysis outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.colors import LogNorm
from matplotlib.figure import Figure


def save_and_maybe_show(
    fig: Figure,
    *,
    output_path: str | Path | None,
    show: bool,
) -> None:
    """Persist and/or display a figure using shared analysis behavior."""

    if output_path is not None:
        fig.savefig(Path(output_path), dpi=150)
    if show:
        plt.show()


def plot_histogram_2d(
    hist: np.ndarray,
    x_edges: np.ndarray,
    y_edges: np.ndarray,
    *,
    title: str,
    cmap: str,
    log_scale: bool,
    output_path: str | Path | None,
    show: bool,
) -> tuple[Figure, Axes]:
    """Render a 2D histogram image to a matplotlib figure."""

    fig, ax = plt.subplots(figsize=(7, 6))

    norm = None
    if log_scale and np.any(hist > 0):
        norm = LogNorm(vmin=1.0, vmax=float(hist.max()))

    image = ax.imshow(
        hist.T,
        origin="lower",
        extent=[x_edges[0], x_edges[-1], y_edges[0], y_edges[-1]],
        interpolation="nearest",
        aspect="equal",
        cmap=cmap,
        norm=norm,
    )

    ax.set_title(title)
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    fig.colorbar(image, ax=ax, label="counts")
    fig.tight_layout()
    save_and_maybe_show(fig, output_path=output_path, show=show)
    return fig, ax


def plot_histogram_1d(
    values: np.ndarray,
    *,
    bin_edges: Sequence[float],
    title: str,
    x_label: str,
    log_scale: bool,
    output_path: str | Path | None,
    show: bool,
) -> tuple[Figure, Axes]:
    """Render a 1D histogram to a matplotlib figure."""

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.hist(
        values,
        bins=bin_edges,
        color="#2f5d80",
        edgecolor="black",
        linewidth=0.5,
        alpha=0.8,
        label="Observed",
    )
    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel("counts")
    if log_scale:
        ax.set_yscale("log")
    fig.tight_layout()
    save_and_maybe_show(fig, output_path=output_path, show=show)
    return fig, ax


def overlay_histogram_colors(count: int) -> list[str]:
    """Return at least `count` histogram colors from the active style cycle."""

    cycle = plt.rcParams.get("axes.prop_cycle")
    colors = list(cycle.by_key().get("color", [])) if cycle is not None else []
    if not colors:
        colors = ["#4c78a8", "#f58518", "#54a24b", "#e45756", "#72b7b2"]
    return [colors[index % len(colors)] for index in range(count)]


__all__ = [
    "overlay_histogram_colors",
    "plot_histogram_1d",
    "plot_histogram_2d",
    "save_and_maybe_show",
]
