#!/usr/bin/env python3

import os
import subprocess
import time
from pathlib import Path

PLAYLIST = "/app/hls/playlist.txt"
OUTPUT = "/app/hls/stream.m3u8"
DEFAULT_ASSETS_ROOT = "/app/assets"
DEFAULT_BUG_IMAGE = "branding/hbn_logo_bug.png"


def resolve_assets_root() -> str:
    override = os.environ.get("HBN_ASSETS_ROOT")
    if override:
        return override

    if os.path.isdir(DEFAULT_ASSETS_ROOT):
        return DEFAULT_ASSETS_ROOT

    repo_guess = os.path.abspath(
        os.path.join(Path(__file__).resolve().parent.parent, "assets")
    )
    if os.path.isdir(repo_guess):
        return repo_guess

    return DEFAULT_ASSETS_ROOT


def get_float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def get_int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return int(default)


ASSETS_ROOT = resolve_assets_root()
BUG_IMAGE_PATH = os.environ.get(
    "HBN_BUG_PATH", os.path.join(ASSETS_ROOT, DEFAULT_BUG_IMAGE)
)
BUG_ALPHA = get_float_env("HBN_BUG_ALPHA", 0.8)
BUG_HEIGHT_FRACTION = get_float_env("HBN_BUG_HEIGHT_FRACTION", 0.12)
BUG_MARGIN = get_int_env("HBN_BUG_MARGIN", 40)
BUG_POSITION = os.environ.get("HBN_BUG_POSITION", "top-right").lower()


def load_playlist():
    if not os.path.exists(PLAYLIST):
        raise FileNotFoundError(f"Playlist not found at {PLAYLIST}")
    with open(PLAYLIST, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def format_number(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def overlay_position_expr(position: str, margin: int) -> tuple[str, str]:
    margin_str = str(margin)
    mapping = {
        "top-left": (margin_str, margin_str),
        "top-right": (f"main_w-overlay_w-{margin_str}", margin_str),
        "bottom-left": (margin_str, f"main_h-overlay_h-{margin_str}"),
        "bottom-right": (
            f"main_w-overlay_w-{margin_str}",
            f"main_h-overlay_h-{margin_str}",
        ),
    }
    return mapping.get(position, mapping["top-right"])


def probe_video_height(src: str) -> int | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=height",
                "-of",
                "csv=p=0",
                src,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        height_str = result.stdout.strip()
        return int(height_str) if height_str else None
    except (subprocess.CalledProcessError, ValueError):
        return None


def build_overlay_args(video_height: int | None):
    if not os.path.isfile(BUG_IMAGE_PATH):
        return [], False

    alpha = format_number(BUG_ALPHA)
    x_expr, y_expr = overlay_position_expr(BUG_POSITION, BUG_MARGIN)

    stages = [
        f"[1]format=rgba,colorchannelmixer=aa={alpha}[logo_base]",
    ]

    logo_stream = "[logo_base]"
    if video_height:
        target_height = max(2, int(video_height * BUG_HEIGHT_FRACTION))
        if target_height % 2:
            target_height += 1

        stages.append(f"{logo_stream}scale=-1:{target_height}[logo_scaled]")
        logo_stream = "[logo_scaled]"

    stages.append(f"[0]{logo_stream}overlay=x={x_expr}:y={y_expr}:shortest=1[vout]")
    filter_expr = ";".join(stages)

    args = [
        "-loop",
        "1",
        "-i",
        BUG_IMAGE_PATH,
        "-filter_complex",
        filter_expr,
        "-map",
        "[vout]",
        "-map",
        "0:a?",
    ]
    return args, True


def stream_file(src):
    print(f"Streaming: {src}", flush=True)
    video_height = probe_video_height(src)
    overlay_args, has_overlay = build_overlay_args(video_height)
    cmd = [
        "ffmpeg",
        "-re",
        "-i",
        src,
    ]
    cmd += overlay_args
    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-maxrate",
        "3000k",
        "-bufsize",
        "6000k",
        "-c:a",
        "aac",
        "-ac",
        "2",
        "-ar",
        "48000",
        "-b:a",
        "128k",
        "-f",
        "hls",
        "-hls_time",
        "6",
        "-hls_list_size",
        "12",
        "-hls_flags",
        "delete_segments+append_list+omit_endlist+discont_start",
        OUTPUT,
    ]
    subprocess.run(cmd, check=False)


def run_stream():
    while True:
        try:
            files = load_playlist()
        except FileNotFoundError as exc:
            print(exc, flush=True)
            time.sleep(5)
            continue

        if not files:
            print("Playlist empty, waiting for media files...", flush=True)
            time.sleep(10)
            continue

        for src in files:
            stream_file(src)


if __name__ == "__main__":
    run_stream()

