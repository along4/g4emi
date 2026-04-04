"""Generate a 2D event-level recoil-path and photon-origin plot from HDF5."""

from __future__ import annotations

import argparse
from pathlib import Path

from matplotlib.artist import Artist
from matplotlib import pyplot as plt

from example_support import (  # noqa: E402
    default_output_dir_from_input,
    ensure_repo_root_on_path,
    infer_transport_hdf5_path,
)

ensure_repo_root_on_path()
from analysis.events import (  # noqa: E402
    event_recoil_paths_to_image,
    random_gun_call_id,
)


def _enable_hover_annotations(fig, ax) -> None:
    """Enable simple hover tooltips for artists carrying `_hover_text`."""

    annotation = ax.annotate(
        "",
        xy=(0.0, 0.0),
        xytext=(12.0, 12.0),
        textcoords="offset points",
        bbox={"boxstyle": "round", "fc": "white", "ec": "0.4", "alpha": 0.95},
        arrowprops={"arrowstyle": "->", "color": "0.35"},
    )
    annotation.set_visible(False)

    artists: list[Artist] = [
        artist
        for artist in ax.get_children()
        if getattr(artist, "_hover_text", None) is not None
    ]

    def _on_move(event) -> None:
        if event.inaxes != ax:
            if annotation.get_visible():
                annotation.set_visible(False)
                fig.canvas.draw_idle()
            return

        for artist in reversed(artists):
            contains, details = artist.contains(event)
            if not contains:
                continue
            x_pos = event.xdata if event.xdata is not None else 0.0
            y_pos = event.ydata if event.ydata is not None else 0.0
            if "ind" in details and hasattr(artist, "get_offsets"):
                offsets = artist.get_offsets()
                index = int(details["ind"][0])
                if len(offsets) > index:
                    x_pos = float(offsets[index][0])
                    y_pos = float(offsets[index][1])
            annotation.xy = (x_pos, y_pos)
            annotation.set_text(str(getattr(artist, "_hover_text")))
            annotation.set_visible(True)
            fig.canvas.draw_idle()
            return

        if annotation.get_visible():
            annotation.set_visible(False)
            fig.canvas.draw_idle()

    fig.canvas.mpl_connect("motion_notify_event", _on_move)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot a random event with recoil paths and linked photon-origin points."
        )
    )
    parser.add_argument(
        "hdf5_path",
        type=Path,
        help="Path to input HDF5 file (e.g. data/.../photon_optical_interface_hits_0000.h5).",
    )
    parser.add_argument(
        "--secondary-species",
        type=str,
        default=None,
        help=(
            "Optional secondary species filter used when choosing the random event "
            "(for example: proton)."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional RNG seed for reproducible random event selection.",
    )
    parser.add_argument(
        "--plane",
        choices=("xy", "xz", "yz"),
        default="xy",
        help="2D projection plane for the real-space view (default: xy).",
    )
    parser.add_argument(
        "--transport-hdf5",
        type=Path,
        default=None,
        help=(
            "Optional transport HDF5 path containing /transported_photons so photon "
            "origins can be colored by whether they reached the intensifier. "
            "Defaults to the sibling transportedPhotons file when inferable."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory for the output PNG "
            "(default: <run_root>/plots when inferable, else <input_dir>/plots)."
        ),
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display the plot interactively instead of writing a PNG.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help=(
            "Open an interactive Matplotlib window with pan/zoom and hover tooltips. "
            "This implies --show."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    hdf5_path = args.hdf5_path.expanduser().resolve()
    if not hdf5_path.exists():
        raise FileNotFoundError(f"Input HDF5 file not found: {hdf5_path}")
    transport_hdf5_path = (
        args.transport_hdf5.expanduser().resolve()
        if args.transport_hdf5 is not None
        else infer_transport_hdf5_path(hdf5_path)
    )
    if transport_hdf5_path is not None and not transport_hdf5_path.exists():
        raise FileNotFoundError(f"Transport HDF5 file not found: {transport_hdf5_path}")
    gun_call_id = random_gun_call_id(
        hdf5_path,
        secondary_species=args.secondary_species,
        seed=args.seed,
    )

    output_dir = None
    should_show = bool(args.show or args.interactive)
    if not should_show:
        output_dir = (
            args.output_dir.expanduser().resolve()
            if args.output_dir is not None
            else default_output_dir_from_input(hdf5_path).resolve()
        )
        output_dir.mkdir(parents=True, exist_ok=True)
    output_path = (
        None
        if output_dir is None
        else output_dir / f"event_{gun_call_id}_{args.plane}_recoil_paths.png"
    )

    fig, ax = event_recoil_paths_to_image(
        hdf5_path,
        gun_call_id,
        plane=args.plane,
        transport_hdf5_path=transport_hdf5_path,
        output_path=output_path,
        show=False,
    )
    if args.interactive:
        _enable_hover_annotations(fig, ax)

    print(f"Input HDF5: {hdf5_path}")
    if transport_hdf5_path is not None:
        print(f"Transport HDF5: {transport_hdf5_path}")
    else:
        print("Transport HDF5: not provided or inferred; photon origins share one color.")
    print(f"secondary_species filter: {args.secondary_species or '(none)'}")
    if args.seed is not None:
        print(f"RNG seed: {args.seed}")
    print(f"Selected gun_call_id: {gun_call_id}")
    print(f"Plane: {args.plane}")
    if args.interactive:
        print("Displaying interactive plot window with hover tooltips.")
        plt.show()
    elif args.show:
        print("Displaying plot interactively.")
        plt.show()
    else:
        print(f"Wrote image: {output_path}")


if __name__ == "__main__":
    main()
