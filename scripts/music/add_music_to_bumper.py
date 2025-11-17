"""
Helpers for blending quiet background music under bumper videos.
"""

from __future__ import annotations

import os
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.bumpers.ffmpeg_utils import run_ffmpeg

DEFAULT_MUSIC_DIR = "/app/assets/music"
SUPPORTED_AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac"}


def resolve_music_dir() -> Path:
    """
    Determine where music assets live.

    Preference order:
      1. $HBN_MUSIC_DIR override (if it exists)
      2. Container default (/app/assets/music)
      3. Repo-local assets/music (useful for local dev)
    """

    override = os.environ.get("HBN_MUSIC_DIR")
    if override:
        path = Path(override).expanduser()
        if path.exists():
            return path

    container_default = Path(DEFAULT_MUSIC_DIR)
    if container_default.exists():
        return container_default

    repo_guess = Path(__file__).resolve().parents[2] / "assets" / "music"
    return repo_guess


def list_music_files(directory: Path) -> list[Path]:
    """
    Return a deterministic, alphabetised list of usable audio tracks.
    """

    if not directory.exists():
        return []

    def is_supported(path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_SUFFIXES

    candidates: Iterable[Path] = directory.iterdir()
    return sorted(
        (path for path in candidates if is_supported(path)),
        key=lambda path: path.name.lower(),
    )


def pick_music_track(tracks: Sequence[Path]) -> Path | None:
    """
    Pick a track at random from the supplied list (if any).
    """

    if not tracks:
        return None
    return random.choice(tracks)


def add_music_to_bumper(
    bumper_video_path: str,
    output_path: str,
    music_track_path: Optional[str] = None,
    music_volume: float = 0.2,
) -> None:
    """
    Mixes a music track underneath the supplied bumper video.
    
    If music_track_path is provided, uses that track. Otherwise picks randomly.

    If no music files exist, the bumper is copied verbatim.
    """

    video = Path(bumper_video_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Use provided track or pick randomly
    if music_track_path:
        track = Path(music_track_path)
        if not track.exists():
            print(f"[Music] Provided track not found: {music_track_path}, picking randomly.")
            track = None
    else:
        track = None
    
    if not track:
        music_dir = resolve_music_dir()
        music_files = list_music_files(music_dir)
        track = pick_music_track(music_files)

    if not track:
        # Nothing to mix, just forward the silent bumper.
        print(f"[Music] No audio tracks found, leaving bumper silent.")
        if video != output:
            shutil.move(str(video), str(output))
        return

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-i",
        str(track),
        "-filter_complex",
        f"[1:a]volume={music_volume}[bg]",
        "-map",
        "0:v",
        "-map",
        "[bg]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(output),
    ]
    try:
        run_ffmpeg(
            cmd,
            timeout=120.0,
            description=f"Adding music to bumper (track: {track.name})",
        )
    finally:
        # Clean up the temporary silent video if it is still around.
        if video.exists() and video != output:
            video.unlink()


def add_random_music_to_bumper(
    bumper_video_path: str,
    output_path: str,
    music_volume: float = 0.2,
) -> None:
    """
    Mixes a randomly chosen music track underneath the supplied bumper video.
    
    This is a convenience wrapper around add_music_to_bumper for backward compatibility.
    """
    add_music_to_bumper(bumper_video_path, output_path, None, music_volume)
