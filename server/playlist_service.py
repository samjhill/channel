"""
Shared helpers for inspecting and updating the generated playlist file.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov")

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_PLAYLIST_PATH = Path("/app/hls/playlist.txt")
FALLBACK_PLAYLIST_PATH = REPO_ROOT / "hls" / "playlist.txt"

DEFAULT_PLAYHEAD_PATH = Path("/app/hls/playhead.json")
FALLBACK_PLAYHEAD_PATH = REPO_ROOT / "hls" / "playhead.json"


def _resolve_path(env_var: str, default_path: Path, fallback_path: Path) -> Path:
    override = os.environ.get(env_var)
    if override:
        return Path(override).expanduser()

    if default_path.exists() or default_path.parent.exists():
        return default_path

    fallback_path.parent.mkdir(parents=True, exist_ok=True)
    return fallback_path


def resolve_playlist_path() -> Path:
    return _resolve_path("CHANNEL_PLAYLIST_PATH", DEFAULT_PLAYLIST_PATH, FALLBACK_PLAYLIST_PATH)


def resolve_playhead_path() -> Path:
    return _resolve_path("CHANNEL_PLAYHEAD_PATH", DEFAULT_PLAYHEAD_PATH, FALLBACK_PLAYHEAD_PATH)


def load_playlist_entries() -> Tuple[List[str], float]:
    playlist_path = resolve_playlist_path()
    if not playlist_path.exists():
        raise FileNotFoundError(f"Playlist not found at {playlist_path}")

    with playlist_path.open("r", encoding="utf-8") as fh:
        entries = [line.strip() for line in fh if line.strip()]

    try:
        mtime = playlist_path.stat().st_mtime
    except FileNotFoundError:
        mtime = time.time()

    return entries, mtime


def write_playlist_entries(entries: Sequence[str]) -> float:
    playlist_path = resolve_playlist_path()
    playlist_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(playlist_path.parent), delete=False
    ) as tmp:
        for entry in entries:
            tmp.write(entry + "\n")
        tmp_path = Path(tmp.name)

    tmp_path.replace(playlist_path)
    try:
        return playlist_path.stat().st_mtime
    except FileNotFoundError:
        return time.time()


def load_playhead_state() -> Dict[str, Any]:
    playhead_path = resolve_playhead_path()
    if not playhead_path.exists():
        return {}
    with playhead_path.open("r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            return {}


def save_playhead_state(state: Dict[str, Any]) -> None:
    playhead_path = resolve_playhead_path()
    playhead_path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = time.time()
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(playhead_path.parent), delete=False
    ) as tmp:
        json.dump(state, tmp, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(playhead_path)


def _normalize_token(value: str) -> str:
    return value.replace("\\", "/").lower()


def is_up_next_bumper(entry: str) -> bool:
    token = _normalize_token(entry)
    return "/bumpers/up_next/" in token


def is_sassy_card(entry: str) -> bool:
    token = _normalize_token(entry)
    return "/bumpers/sassy/" in token


def entry_type(entry: str) -> str:
    token = _normalize_token(entry)
    if is_up_next_bumper(entry):
        return "bumper"
    if is_sassy_card(entry):
        return "sassy"
    if token.endswith(VIDEO_EXTENSIONS):
        return "episode"
    return "other"


def is_episode_entry(entry: str) -> bool:
    return entry_type(entry) == "episode"


def build_playlist_segments(entries: Sequence[str]) -> List[Dict[str, Any]]:
    """
    Collapse the low-level playlist entries (bumpers + episodes + cards) into
    logical episode segments so they can be re-ordered safely.
    """

    segments: List[Dict[str, Any]] = []
    idx = 0
    total = len(entries)

    while idx < total:
        entry = entries[idx]
        if not is_episode_entry(entry):
            idx += 1
            continue

        start = idx
        if idx > 0 and is_up_next_bumper(entries[idx - 1]):
            start = idx - 1

        end = idx + 1
        if end < total and is_sassy_card(entries[end]):
            end += 1

        segment_entries = list(entries[start:end])
        segment = {
            "episode_path": entry,
            "entries": segment_entries,
            "start": start,
            "end": end,
            "index": len(segments),
        }
        segments.append(segment)
        idx = end

    return segments


def find_segment_index_for_entry(segments: Sequence[Dict[str, Any]], entry_path: str) -> int:
    for idx, segment in enumerate(segments):
        if entry_path in segment.get("entries", []):
            return idx
    return -1


def _safe_path(path_str: str) -> Path:
    return Path(path_str).expanduser()


def _relative_media_path(path_str: str, media_root: Optional[str]) -> str:
    if not media_root:
        return path_str
    try:
        media_root_path = _safe_path(media_root).resolve(strict=False)
        target_path = _safe_path(path_str).resolve(strict=False)
        return str(target_path.relative_to(media_root_path))
    except Exception:
        return path_str


def describe_episode(path_str: str, media_root: Optional[str], position: int) -> Dict[str, Any]:
    rel_path = _relative_media_path(path_str, media_root)
    target = _safe_path(path_str)
    filename = target.name or rel_path
    parent = target.parent.name

    label = parent or filename
    detail = filename if parent else rel_path

    return {
        "path": path_str,
        "label": label,
        "detail": detail,
        "relative_path": rel_path,
        "filename": filename,
        "type": "episode",
        "controllable": True,
        "position": position,
    }


def flatten_segments(segments: Iterable[Dict[str, Any]]) -> List[str]:
    flattened: List[str] = []
    for segment in segments:
        flattened.extend(segment.get("entries", []))
    return flattened


