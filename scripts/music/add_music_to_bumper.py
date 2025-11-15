"""
Helpers for blending quiet background music under bumper videos.
"""

from __future__ import annotations

import os
import random
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Sequence

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


def add_random_music_to_bumper(
    bumper_video_path: str,
    output_path: str,
    music_volume: float = 0.2,
) -> None:
    """
    Mixes a randomly chosen music track underneath the supplied bumper video.

    If no music files exist, the bumper is copied verbatim.
    """

    video = Path(bumper_video_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    music_dir = resolve_music_dir()
    music_files = list_music_files(music_dir)
    track = pick_music_track(music_files)

    if not track:
        # Nothing to mix, just forward the silent bumper.
        print(f"[Music] No audio tracks found in {music_dir}, leaving bumper silent.")
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
        subprocess.run(cmd, check=True)
    finally:
        # Clean up the temporary silent video if it is still around.
        if video.exists():
            video.unlink()

