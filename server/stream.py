#!/usr/bin/env python3

import os
import subprocess
import time
from pathlib import Path
from typing import Dict

try:
    from playlist_service import (
        entry_type,
        load_playlist_entries,
        resolve_playlist_path,
        save_playhead_state,
    )
except ImportError:
    # Fallback for local development outside Docker
    import sys
    from pathlib import Path
    repo_root = Path(__file__).resolve().parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from server.playlist_service import (
        entry_type,
        load_playlist_entries,
        resolve_playlist_path,
        save_playhead_state,
    )

PLAYLIST = str(resolve_playlist_path())
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

# Cache for video height probing (expensive operation)
_video_height_cache: Dict[str, int | None] = {}


def load_playlist():
    entries, mtime = load_playlist_entries()
    return [entry for entry in entries if entry], mtime


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
    """Probe video height with caching to avoid repeated ffprobe calls."""
    global _video_height_cache
    
    # Check cache first
    if src in _video_height_cache:
        return _video_height_cache[src]
    
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
        height = int(height_str) if height_str else None
    except (subprocess.CalledProcessError, ValueError):
        height = None
    
    # Cache the result (even if None to avoid repeated failures)
    _video_height_cache[src] = height
    return height


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
        "-g",
        "60",
        "-sc_threshold",
        "0",
        "-force_key_frames",
        "expr:gte(t,n_forced*6)",
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
        "30",
        "-hls_flags",
        "delete_segments+append_list+omit_endlist+discont_start",
        "-hls_segment_type",
        "mpegts",
        "-hls_segment_filename",
        "/app/hls/stream%04d.ts",
        OUTPUT,
    ]
    subprocess.run(cmd, check=False)


def record_playhead(src: str, index: int, playlist_mtime: float) -> None:
    state = {
        "current_path": src,
        "current_index": index,
        "playlist_mtime": playlist_mtime,
        "playlist_path": PLAYLIST,
        "entry_type": entry_type(src),
    }
    save_playhead_state(state)


def run_stream():
    last_played: str | None = None
    next_index = 0

    while True:
        try:
            files, playlist_mtime = load_playlist()
        except FileNotFoundError as exc:
            print(exc, flush=True)
            time.sleep(5)
            continue

        if not files:
            print("Playlist empty, waiting for media files...", flush=True)
            time.sleep(10)
            continue

        if last_played:
            try:
                next_index = files.index(last_played) + 1
            except ValueError:
                next_index = 0
        else:
            next_index = 0

        while files:
            if next_index >= len(files):
                next_index = 0

            src = files[next_index]
            record_playhead(src, next_index, playlist_mtime)
            stream_file(src)
            last_played = src

            try:
                files, playlist_mtime = load_playlist()
            except FileNotFoundError as exc:
                print(exc, flush=True)
                time.sleep(5)
                break

            if not files:
                print("Playlist empty after update, waiting...", flush=True)
                time.sleep(10)
                break

            # Optimize: only search if we need to find the next position
            # If playlist didn't change, just increment
            if next_index < len(files) and files[next_index] == last_played:
                next_index += 1
            else:
                try:
                    next_index = files.index(last_played) + 1
                except ValueError:
                    next_index = 0


if __name__ == "__main__":
    run_stream()

