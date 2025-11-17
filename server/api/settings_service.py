"""
Helpers for reading and writing channel configuration settings.
"""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

CONFIG_PATH = Path(__file__).parent.parent / "config" / "channel_settings.json"
CONTAINER_CONFIG_PATH = Path("/app/config/channel_settings.json")

DEFAULT_CHANNEL_ID = "hbn-main"
DEFAULT_CHANNEL_NAME = "Hillside Broadcasting Network"
DEFAULT_MEDIA_ROOT = "/media/tvchannel"

CHANNEL_PLAYBACK_MODES = {"sequential", "random"}
SHOW_PLAYBACK_MODES = {"inherit", "sequential", "random"}

# Cache for settings and path resolution
_settings_cache: Optional[Dict[str, Any]] = None
_settings_mtime: float = 0.0
_config_path_cache: Optional[Path] = None
_channels_index: Dict[str, Dict[str, Any]] = {}


def _resolve_config_path() -> Path:
    """Resolve config path with caching."""
    global _config_path_cache

    if _config_path_cache is not None:
        return _config_path_cache

    override = os.environ.get("CHANNEL_CONFIG")
    if override:
        _config_path_cache = Path(override).expanduser()
        return _config_path_cache

    if CONTAINER_CONFIG_PATH.exists() or CONTAINER_CONFIG_PATH.parent.exists():
        _config_path_cache = CONTAINER_CONFIG_PATH
        return _config_path_cache

    _config_path_cache = CONFIG_PATH
    return _config_path_cache


def _invalidate_settings_cache() -> None:
    """Invalidate the settings cache."""
    global _settings_cache, _settings_mtime, _channels_index
    _settings_cache = None
    _settings_mtime = 0.0
    _channels_index = {}


def slugify(text: str, fallback: str = "channel") -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned or fallback


def default_channel_template() -> Dict[str, Any]:
    return {
        "id": DEFAULT_CHANNEL_ID,
        "name": DEFAULT_CHANNEL_NAME,
        "enabled": True,
        "media_root": DEFAULT_MEDIA_ROOT,
        "playback_mode": "sequential",
        "loop_entire_library": True,
        "shows": [],
        "bumpers": {"enable_up_next": True, "enable_intermission": True},
        "branding": {"show_bug_overlay": True},
    }


def migrate_legacy_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    channel = default_channel_template()
    shows = data.get("include_shows") or []
    normalized_shows = []

    for raw in shows:
        label = str(raw).strip()
        if not label:
            continue
        normalized_shows.append(
            normalize_show(
                {
                    "label": label,
                    "path": label,
                    "include": True,
                    "playback_mode": "inherit",
                    "weight": 1.0,
                }
            )
        )

    if not normalized_shows:
        normalized_shows = [
            normalize_show(
                {
                    "label": "Sample Show",
                    "path": "Sample Show",
                    "include": True,
                }
            )
        ]

    channel["shows"] = normalized_shows
    return {"channels": [channel]}


def normalize_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        data = {}

    channels = data.get("channels")
    if not isinstance(channels, list):
        return migrate_legacy_settings(data)

    normalized_channels = []
    for channel in channels:
        if not isinstance(channel, dict):
            continue
        normalized_channels.append(normalize_channel(channel))

    if not normalized_channels:
        normalized_channels = [default_channel_template()]

    normalized = deepcopy(data)
    normalized["channels"] = normalized_channels
    return normalized


def normalize_channel(channel: Dict[str, Any]) -> Dict[str, Any]:
    normalized = deepcopy(channel) if isinstance(channel, dict) else {}

    name = str(normalized.get("name") or DEFAULT_CHANNEL_NAME).strip()
    channel_id = normalized.get("id") or slugify(name or DEFAULT_CHANNEL_ID)

    normalized["id"] = channel_id
    normalized["name"] = name or DEFAULT_CHANNEL_NAME
    normalized["enabled"] = bool(normalized.get("enabled", True))

    media_root = normalized.get("media_root") or DEFAULT_MEDIA_ROOT
    normalized["media_root"] = str(media_root)

    playback = normalized.get("playback_mode", "sequential")
    if playback not in CHANNEL_PLAYBACK_MODES:
        playback = "sequential"
    normalized["playback_mode"] = playback

    normalized["loop_entire_library"] = bool(
        normalized.get("loop_entire_library", True)
    )

    shows = normalized.get("shows") or []
    normalized_shows = []
    for show in shows:
        if isinstance(show, dict):
            normalized_shows.append(normalize_show(show))
    normalized["shows"] = normalized_shows

    if "bumpers" not in normalized:
        normalized["bumpers"] = {"enable_up_next": True, "enable_intermission": True}
    if "branding" not in normalized:
        normalized["branding"] = {"show_bug_overlay": True}

    return normalized


def normalize_show(show: Dict[str, Any]) -> Dict[str, Any]:
    normalized = deepcopy(show) if isinstance(show, dict) else {}

    label = str(
        normalized.get("label")
        or normalized.get("name")
        or normalized.get("id")
        or "Show"
    ).strip()
    if not label:
        label = "Show"

    show_id = normalized.get("id") or slugify(label, fallback="show")
    normalized["id"] = show_id
    normalized["label"] = label
    normalized["path"] = str(normalized.get("path") or label)
    normalized["include"] = bool(normalized.get("include", True))

    playback = normalized.get("playback_mode", "inherit")
    if playback not in SHOW_PLAYBACK_MODES:
        playback = "inherit"
    normalized["playback_mode"] = playback

    weight = normalized.get("weight", 1.0)
    try:
        weight = float(weight)
    except (TypeError, ValueError):
        weight = 1.0
    normalized["weight"] = max(0.1, min(weight, 5.0))

    return normalized


def validate_settings(data: Dict[str, Any]) -> None:
    if "channels" not in data or not isinstance(data["channels"], list):
        raise ValueError("Settings must include a 'channels' list.")
    if not data["channels"]:
        raise ValueError("At least one channel must be configured.")


def load_settings() -> Dict[str, Any]:
    """Load settings with mtime-based caching."""
    global _settings_cache, _settings_mtime, _channels_index

    config_path = _resolve_config_path()

    # Check if file exists and get mtime
    if config_path.exists():
        try:
            current_mtime = config_path.stat().st_mtime
        except OSError:
            current_mtime = 0.0
    else:
        current_mtime = 0.0

    # Return cached version if file hasn't changed
    if _settings_cache is not None and abs(current_mtime - _settings_mtime) < 0.001:
        return _settings_cache

    # Load and normalize settings
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
    else:
        raw = {}

    normalized = normalize_settings(raw)
    if normalized != raw:
        save_settings(normalized)
        # Re-read mtime after save
        if config_path.exists():
            try:
                current_mtime = config_path.stat().st_mtime
            except OSError:
                current_mtime = 0.0

    # Update cache
    _settings_cache = normalized
    _settings_mtime = current_mtime

    # Build channel index for O(1) lookups
    _channels_index = {ch.get("id"): ch for ch in normalized.get("channels", [])}

    return normalized


def save_settings(data: Dict[str, Any]) -> None:
    normalized = normalize_settings(data)
    validate_settings(normalized)
    config_path = _resolve_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as fh:
        json.dump(normalized, fh, indent=2)
    # Invalidate cache after save
    _invalidate_settings_cache()


def list_channels() -> List[Dict[str, Any]]:
    """List all channels, using cached settings."""
    return load_settings().get("channels", [])


def get_channel(channel_id: str) -> Optional[Dict[str, Any]]:
    """Get channel by ID with O(1) lookup using cached index."""
    # Ensure cache is loaded
    load_settings()
    # Use index for O(1) lookup instead of linear search
    return _channels_index.get(channel_id)


def replace_channel(channel_id: str, new_data: Dict[str, Any]) -> Dict[str, Any]:
    settings = load_settings()
    updated_channel = normalize_channel(new_data)
    updated_channel["id"] = channel_id

    channels = settings.get("channels", [])
    # Use index to find channel faster
    if channel_id in _channels_index:
        for idx, channel in enumerate(channels):
            if channel.get("id") == channel_id:
                channels[idx] = updated_channel
                break
    else:
        raise KeyError(f"Channel '{channel_id}' not found.")

    next_settings = deepcopy(settings)
    next_settings["channels"] = channels
    save_settings(next_settings)
    return updated_channel
