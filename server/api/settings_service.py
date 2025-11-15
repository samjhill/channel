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


def _resolve_config_path() -> Path:
    override = os.environ.get("CHANNEL_CONFIG")
    if override:
        return Path(override).expanduser()

    if CONTAINER_CONFIG_PATH.exists() or CONTAINER_CONFIG_PATH.parent.exists():
        return CONTAINER_CONFIG_PATH

    return CONFIG_PATH


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

    normalized["loop_entire_library"] = bool(normalized.get("loop_entire_library", True))

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
    config_path = _resolve_config_path()
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
    else:
        raw = {}

    normalized = normalize_settings(raw)
    if normalized != raw:
        save_settings(normalized)
    return normalized


def save_settings(data: Dict[str, Any]) -> None:
    normalized = normalize_settings(data)
    validate_settings(normalized)
    config_path = _resolve_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as fh:
        json.dump(normalized, fh, indent=2)


def list_channels() -> List[Dict[str, Any]]:
    return load_settings().get("channels", [])


def get_channel(channel_id: str) -> Optional[Dict[str, Any]]:
    for channel in list_channels():
        if channel.get("id") == channel_id:
            return channel
    return None


def replace_channel(channel_id: str, new_data: Dict[str, Any]) -> Dict[str, Any]:
    settings = load_settings()
    updated_channel = normalize_channel(new_data)
    updated_channel["id"] = channel_id

    channels = settings.get("channels", [])
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


