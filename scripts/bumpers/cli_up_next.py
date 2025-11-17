"""CLI for rendering HBN Up Next bumpers."""

import argparse
import os

from .render_up_next import render_up_next_bumper


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a 6-second HBN Up Next bumper."
    )
    parser.add_argument("--title", required=True, help="Show title to display")
    parser.add_argument(
        "--out",
        required=True,
        help="Output path for the MP4 (e.g., assets/bumpers/up_next/show.mp4)",
    )
    parser.add_argument("--width", type=int, default=1600, help="Video width in pixels")
    parser.add_argument(
        "--height", type=int, default=900, help="Video height in pixels"
    )
    parser.add_argument(
        "--duration-sec", type=float, default=6.0, help="Duration in seconds"
    )
    parser.add_argument("--fps", type=int, default=30, help="Frames per second")
    parser.add_argument(
        "--logo-path",
        default="assets/branding/hbn_logo_bug.png",
        help="Path to the logo PNG",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Optional random seed for deterministic rendering",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = os.path.abspath(args.out)
    render_up_next_bumper(
        show_title=args.title,
        output_path=output_path,
        width=args.width,
        height=args.height,
        duration_sec=args.duration_sec,
        fps=args.fps,
        logo_path=args.logo_path,
        seed=args.seed,
    )
    print(f"Rendered bumper for '{args.title}' → {output_path}")


if __name__ == "__main__":
    main()
