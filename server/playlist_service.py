"""
Shared helpers for inspecting and updating the generated playlist file.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# File locking support (cross-platform)
try:
    import fcntl  # Linux/macOS
except ImportError:
    fcntl = None  # type: ignore

try:
    import msvcrt  # Windows
except ImportError:
    msvcrt = None  # type: ignore

LOGGER = logging.getLogger(__name__)

VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov")

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_PLAYLIST_PATH = Path("/app/hls/playlist.txt")
FALLBACK_PLAYLIST_PATH = REPO_ROOT / "hls" / "playlist.txt"

DEFAULT_PLAYHEAD_PATH = Path("/app/hls/playhead.json")
FALLBACK_PLAYHEAD_PATH = REPO_ROOT / "hls" / "playhead.json"

DEFAULT_WATCH_PROGRESS_PATH = Path("/app/hls/watch_progress.json")
FALLBACK_WATCH_PROGRESS_PATH = REPO_ROOT / "hls" / "watch_progress.json"

# Cache for paths, playlist entries, and playhead state
_playlist_path_cache: Optional[Path] = None
_playhead_path_cache: Optional[Path] = None
_watch_progress_path_cache: Optional[Path] = None
_playlist_cache: Optional[Tuple[List[str], float]] = None
_playlist_mtime: float = 0.0
_playhead_cache: Optional[Dict[str, Any]] = None
_playhead_mtime: float = 0.0
_watch_progress_cache: Optional[Dict[str, Any]] = None
_watch_progress_mtime: float = 0.0


def _resolve_path(env_var: str, default_path: Path, fallback_path: Path) -> Path:
    override = os.environ.get(env_var)
    if override:
        return Path(override).expanduser()

    if default_path.exists() or default_path.parent.exists():
        return default_path

    fallback_path.parent.mkdir(parents=True, exist_ok=True)
    return fallback_path


def resolve_playlist_path() -> Path:
    """Resolve playlist path with caching."""
    global _playlist_path_cache

    if _playlist_path_cache is not None:
        return _playlist_path_cache

    _playlist_path_cache = _resolve_path(
        "CHANNEL_PLAYLIST_PATH", DEFAULT_PLAYLIST_PATH, FALLBACK_PLAYLIST_PATH
    )
    return _playlist_path_cache


def resolve_playhead_path() -> Path:
    """Resolve playhead path with caching."""
    global _playhead_path_cache

    if _playhead_path_cache is not None:
        return _playhead_path_cache

    _playhead_path_cache = _resolve_path(
        "CHANNEL_PLAYHEAD_PATH", DEFAULT_PLAYHEAD_PATH, FALLBACK_PLAYHEAD_PATH
    )
    return _playhead_path_cache


def load_playlist_entries() -> Tuple[List[str], float]:
    """Load playlist entries with mtime-based caching."""
    global _playlist_cache, _playlist_mtime

    playlist_path = resolve_playlist_path()
    if not playlist_path.exists():
        raise FileNotFoundError(f"Playlist not found at {playlist_path}")

    # Check mtime to see if cache is still valid
    try:
        current_mtime = playlist_path.stat().st_mtime
    except (FileNotFoundError, OSError):
        current_mtime = time.time()

    # Return cached version if file hasn't changed
    if _playlist_cache is not None and abs(current_mtime - _playlist_mtime) < 0.001:
        return _playlist_cache

    # Load from file
    with playlist_path.open("r", encoding="utf-8") as fh:
        entries = [line.strip() for line in fh if line.strip()]

    # Update cache
    _playlist_cache = (entries, current_mtime)
    _playlist_mtime = current_mtime

    return _playlist_cache


def write_playlist_entries(entries: Sequence[str]) -> float:
    """Write playlist entries and invalidate cache."""
    global _playlist_cache, _playlist_mtime

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
        mtime = playlist_path.stat().st_mtime
    except FileNotFoundError:
        mtime = time.time()

    # Invalidate cache after write
    _playlist_cache = None
    _playlist_mtime = 0.0

    return mtime


def load_playhead_state(force_reload: bool = False) -> Dict[str, Any]:
    """Load playhead state with mtime-based caching.

    Note: Cache is checked every call, so frequent calls will still see updates.
    For real-time skip detection, the streamer should call this frequently.

    Args:
        force_reload: If True, bypass cache and reload from file immediately.
    """
    global _playhead_cache, _playhead_mtime

    playhead_path = resolve_playhead_path()
    if not playhead_path.exists():
        _playhead_cache = {}
        _playhead_mtime = 0.0
        return {}

    # Check mtime to see if cache is still valid
    try:
        current_mtime = playhead_path.stat().st_mtime
    except (FileNotFoundError, OSError):
        current_mtime = 0.0

    # Force reload if requested, or if file has changed
    # Use a very small threshold (0.01s) to detect changes quickly
    if (
        force_reload
        or _playhead_cache is None
        or abs(current_mtime - _playhead_mtime) > 0.01
    ):
        # Load from file
        with playhead_path.open("r", encoding="utf-8") as fh:
            try:
                state = json.load(fh)
            except json.JSONDecodeError:
                state = {}

        # Update cache
        _playhead_cache = state
        _playhead_mtime = current_mtime

    return _playhead_cache


def save_playhead_state(state: Dict[str, Any]) -> None:
    """Save playhead state and update cache."""
    global _playhead_cache, _playhead_mtime

    playhead_path = resolve_playhead_path()
    playhead_path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = time.time()

    # Write to temp file first, then replace (atomic write)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(playhead_path.parent), delete=False
    ) as tmp:
        json.dump(state, tmp, indent=2)
        tmp_path = Path(tmp.name)

    # Atomic replace
    tmp_path.replace(playhead_path)

    # Force filesystem sync to ensure the write is visible immediately
    # This is important for Docker volume mounts
    try:
        import os

        os.fsync(
            playhead_path.fileno()
            if hasattr(playhead_path, "fileno")
            else playhead_path.open("r").fileno()
        )
    except (AttributeError, OSError):
        # Fallback: just ensure the file is written
        pass

    # Update cache after write
    try:
        _playhead_mtime = playhead_path.stat().st_mtime
    except (FileNotFoundError, OSError):
        _playhead_mtime = time.time()
    _playhead_cache = state


def _normalize_token(value: str) -> str:
    return value.replace("\\", "/").lower()


def is_up_next_bumper(entry: str) -> bool:
    token = _normalize_token(entry)
    return "/bumpers/up_next/" in token


def is_sassy_card(entry: str) -> bool:
    token = _normalize_token(entry)
    return "/bumpers/sassy/" in token


def is_network_bumper(entry: str) -> bool:
    token = _normalize_token(entry)
    return "/bumpers/network/" in token


def is_weather_bumper(entry: str) -> bool:
    """Check if an entry is a weather bumper marker."""
    token = _normalize_token(entry)
    return token == "weather_bumper" or "/bumpers/weather/" in token


def entry_type(entry: str) -> str:
    token = _normalize_token(entry)
    if is_up_next_bumper(entry):
        return "bumper"
    if is_sassy_card(entry):
        return "sassy"
    if is_network_bumper(entry):
        return "network"
    if is_weather_bumper(entry):
        return "weather"
    if token.endswith(VIDEO_EXTENSIONS):
        return "episode"
    return "other"


def is_episode_entry(entry: str) -> bool:
    return entry_type(entry) == "episode"


def build_playlist_segments(entries: Sequence[str]) -> List[Dict[str, Any]]:
    """
    Collapse the low-level playlist entries (bumpers + episodes + cards + network bumpers) into
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
        if end < total and is_weather_bumper(entries[end]):
            end += 1
        if end < total and is_sassy_card(entries[end]):
            end += 1
        if end < total and is_network_bumper(entries[end]):
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


# Cache for path normalization to avoid repeated string operations
_path_normalization_cache: Dict[str, str] = {}
_MAX_PATH_CACHE_SIZE = 5000


def _normalize_path(path: str) -> str:
    """Normalize path for comparison, handling container vs host path differences.

    Normalizes both container paths (/media/tvchannel/...) and host paths
    (/Volumes/media/tv/...) to a canonical form for comparison.
    Uses caching to avoid repeated string operations.
    """
    if not path:
        return path

    # Check cache first
    if path in _path_normalization_cache:
        return _path_normalization_cache[path]

    # Normalize the path
    normalized = path
    # Convert container paths to host paths for comparison
    # /media/tvchannel/... -> /Volumes/media/tv/...
    if path.startswith("/media/tvchannel/"):
        normalized = path.replace("/media/tvchannel/", "/Volumes/media/tv/", 1)
    # Keep host paths as-is (they're already in canonical form)

    # Cache the result (with size limit to prevent memory issues)
    if len(_path_normalization_cache) >= _MAX_PATH_CACHE_SIZE:
        # Remove oldest 10% of entries
        keys_to_remove = list(_path_normalization_cache.keys())[
            : _MAX_PATH_CACHE_SIZE // 10
        ]
        for key in keys_to_remove:
            del _path_normalization_cache[key]

    _path_normalization_cache[path] = normalized
    return normalized


def find_segment_index_for_entry(
    segments: Sequence[Dict[str, Any]], entry_path: str
) -> int:
    """Find segment index for an entry path, optimized with early exit."""
    # Normalize the entry path for comparison
    normalized_entry = _normalize_path(entry_path)

    # Use a set for O(1) lookup within entries
    for idx, segment in enumerate(segments):
        entries = segment.get("entries", [])
        episode_path = segment.get("episode_path")

        # Check episode_path first (most common case) - normalize both for comparison
        if episode_path and _normalize_path(episode_path) == normalized_entry:
            return idx

        # Then check entries list - normalize each entry for comparison
        for entry in entries:
            if _normalize_path(entry) == normalized_entry:
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


def describe_episode(
    path_str: str, media_root: Optional[str], position: int
) -> Dict[str, Any]:
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


def resolve_watch_progress_path() -> Path:
    """Resolve watch progress path with caching."""
    global _watch_progress_path_cache

    if _watch_progress_path_cache is not None:
        return _watch_progress_path_cache

    _watch_progress_path_cache = _resolve_path(
        "CHANNEL_WATCH_PROGRESS_PATH",
        DEFAULT_WATCH_PROGRESS_PATH,
        FALLBACK_WATCH_PROGRESS_PATH,
    )
    return _watch_progress_path_cache


def _lock_file(file_handle) -> None:
    """Lock a file handle for exclusive access (cross-platform)."""
    if fcntl:
        # Linux/macOS
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX)
    elif msvcrt:
        # Windows
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_LOCK, 1)
    # If neither is available, continue without locking (graceful degradation)


def _unlock_file(file_handle) -> None:
    """Unlock a file handle (cross-platform)."""
    if fcntl:
        # Linux/macOS
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
    elif msvcrt:
        # Windows
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
    # If neither is available, no-op


def load_watch_progress() -> Dict[str, Any]:
    """
    Load watch progress state with mtime-based caching and file locking.
    Returns a dict mapping episode paths to their watch status.
    Format: { "episode_path": { "watched": bool, "watched_at": float, ... }, ... }
    """
    global _watch_progress_cache, _watch_progress_mtime

    progress_path = resolve_watch_progress_path()
    if not progress_path.exists():
        _watch_progress_cache = {
            "episodes": {},
            "last_watched": None,
            "updated_at": 0.0,
        }
        _watch_progress_mtime = 0.0
        return _watch_progress_cache

    # Check mtime to see if cache is still valid
    try:
        current_mtime = progress_path.stat().st_mtime
    except (FileNotFoundError, OSError):
        current_mtime = 0.0

    # Return cached version if file hasn't changed
    if (
        _watch_progress_cache is not None
        and abs(current_mtime - _watch_progress_mtime) < 0.001
    ):
        return _watch_progress_cache

    # Load from file with locking
    try:
        with progress_path.open("r", encoding="utf-8") as fh:
            _lock_file(fh)
            try:
                progress = json.load(fh)
                # Ensure required keys exist
                if "episodes" not in progress:
                    progress["episodes"] = {}
                if "last_watched" not in progress:
                    progress["last_watched"] = None
            except json.JSONDecodeError as e:
                LOGGER.warning(
                    "Failed to parse watch progress file: %s. Using defaults.", e
                )
                progress = {"episodes": {}, "last_watched": None, "updated_at": 0.0}
            finally:
                _unlock_file(fh)
    except (OSError, IOError) as e:
        LOGGER.warning("Failed to read watch progress file: %s. Using defaults.", e)
        progress = {"episodes": {}, "last_watched": None, "updated_at": 0.0}

    # Update cache
    _watch_progress_cache = progress
    _watch_progress_mtime = current_mtime

    return _watch_progress_cache


def save_watch_progress(progress: Dict[str, Any]) -> None:
    """Save watch progress state with file locking and update cache."""
    global _watch_progress_cache, _watch_progress_mtime

    progress_path = resolve_watch_progress_path()
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress["updated_at"] = time.time()

    # Write to temp file first, then replace (atomic write)
    # Use locking on the temp file to prevent concurrent writes
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(progress_path.parent), delete=False
    ) as tmp:
        try:
            _lock_file(tmp)
            try:
                json.dump(progress, tmp, indent=2)
                tmp.flush()
                os.fsync(tmp.fileno())  # Force write to disk
            finally:
                _unlock_file(tmp)
        except (OSError, IOError) as e:
            LOGGER.error("Failed to write watch progress to temp file: %s", e)
            raise
        tmp_path = Path(tmp.name)

    # Atomic replace
    try:
        tmp_path.replace(progress_path)
        # Force filesystem sync
        try:
            with progress_path.open("r") as fh:
                os.fsync(fh.fileno())
        except (OSError, AttributeError):
            pass  # Graceful degradation if fsync fails
    except (OSError, IOError) as e:
        LOGGER.error("Failed to replace watch progress file: %s", e)
        # Clean up temp file
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise

    # Update cache after write
    try:
        _watch_progress_mtime = progress_path.stat().st_mtime
    except (FileNotFoundError, OSError):
        _watch_progress_mtime = time.time()
    _watch_progress_cache = progress


def mark_episode_watched(episode_path: str, max_entries: int = 10000) -> None:
    """Mark an episode as watched. Automatically cleans up old entries if max_entries exceeded."""
    progress = load_watch_progress()
    if "episodes" not in progress:
        progress["episodes"] = {}

    progress["episodes"][episode_path] = {
        "watched": True,
        "watched_at": time.time(),
    }
    progress["last_watched"] = episode_path

    # Clean up old entries if we exceed max_entries to prevent file growth
    if len(progress["episodes"]) > max_entries:
        # Sort by watched_at timestamp and keep only the most recent entries
        episodes = progress["episodes"]
        sorted_episodes = sorted(
            episodes.items(),
            key=lambda x: x[1].get("watched_at", 0.0),
            reverse=True,
        )
        # Keep the most recent max_entries entries
        progress["episodes"] = dict(sorted_episodes[:max_entries])
        # Ensure last_watched is still in the dict
        if episode_path not in progress["episodes"]:
            progress["episodes"][episode_path] = {
                "watched": True,
                "watched_at": time.time(),
            }

    save_watch_progress(progress)


def is_episode_watched(episode_path: str) -> bool:
    """Check if an episode has been watched."""
    progress = load_watch_progress()
    episode_data = progress.get("episodes", {}).get(episode_path, {})
    return episode_data.get("watched", False)


def get_last_watched_episode() -> Optional[str]:
    """Get the path of the last watched episode."""
    progress = load_watch_progress()
    return progress.get("last_watched")
