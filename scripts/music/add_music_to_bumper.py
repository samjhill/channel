"""
Helpers for blending quiet background music under bumper videos.
"""

from __future__ import annotations

import os
import random
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List

DEFAULT_MUSIC_DIR = "/app/assets/music"


def resolve_music_dir() -> Path:
    override = os.environ.get("HBN_MUSIC_DIR")
    if override:
        path = Path(override).expanduser()
        if path.exists():
            return path

    container_default = Path(DEFAULT_MUSIC_DIR)
    if container_default.exists():
        return container_default

    repo_guess = (
        Path(__file__).resolve().parents[2] / "assets" / "music"
    )
    return repo_guess


def list_music_files(directory: Path) -> List[Path]:
    if not directory.exists():
        return []
    candidates: Iterable[Path] = directory.iterdir()
    return [
        path
        for path in candidates
        if path.is_file() and path.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac"}
    ]


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
    music_dir = resolve_music_dir()
    music_files = list_music_files(music_dir)

    if not music_files:
        # Nothing to mix, just forward the silent bumper.
        shutil.move(str(video), str(output))
        return

    track = random.choice(music_files)
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
    subprocess.run(cmd, check=True)

