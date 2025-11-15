"""
FastAPI application exposing channel configuration management endpoints.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .media_control import restart_media_server
from .settings_service import (
    get_channel,
    list_channels,
    normalize_show,
    replace_channel,
    slugify,
)
from ..playlist_service import (
    build_playlist_segments,
    describe_episode,
    find_segment_index_for_entry,
    flatten_segments,
    load_playhead_state,
    load_playlist_entries,
    write_playlist_entries,
)

app = FastAPI(title="Channel Admin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PlaylistUpdateRequest(BaseModel):
    version: float = Field(..., description="Last-known playlist mtime.")
    desired: List[str] = Field(
        default_factory=list,
        description="Controllable episode paths ordered as they should appear next.",
    )
    skipped: List[str] = Field(
        default_factory=list,
        description="Episode paths to remove from the upcoming window.",
    )


@app.get("/api/healthz")
def health_check() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/channels")
def get_channels() -> List[Dict[str, Any]]:
    return list_channels()


@app.get("/api/channels/{channel_id}")
def get_channel_detail(channel_id: str) -> Dict[str, Any]:
    channel = get_channel(channel_id)
    if channel:
        return channel
    raise HTTPException(status_code=404, detail="Channel not found")


@app.put("/api/channels/{channel_id}")
def update_channel(channel_id: str, updated: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(updated, dict):
        raise HTTPException(status_code=400, detail="Invalid request body")

    body_id = updated.get("id")
    if body_id and body_id != channel_id:
        raise HTTPException(status_code=400, detail="Channel ID mismatch")

    try:
        saved = replace_channel(channel_id, updated)
    except KeyError:
        raise HTTPException(status_code=404, detail="Channel not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    restart_media_server()
    return saved


@app.get("/api/channels/{channel_id}/shows/discover")
def discover_channel_shows(
    channel_id: str,
    media_root: str | None = Query(
        default=None, description="Override the channel's media root when scanning"
    ),
) -> List[Dict[str, Any]]:
    channel = get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    base_path = Path(media_root or channel.get("media_root") or "").expanduser()
    if not base_path.exists():
        return []

    shows: List[Dict[str, Any]] = []
    try:
        for child in sorted(base_path.iterdir()):
            if not child.is_dir():
                continue
            rel_path = child.relative_to(base_path)
            shows.append(
                normalize_show(
                    {
                        "id": slugify(child.name, fallback="show"),
                        "label": child.name,
                        "path": rel_path.as_posix(),
                        "include": True,
                    }
                )
            )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return shows


@app.get("/api/channels/{channel_id}/playlist/next")
def get_upcoming_playlist(
    channel_id: str, limit: int = Query(default=25, ge=1, le=100)
) -> Dict[str, Any]:
    return build_playlist_snapshot(channel_id, limit)


@app.post("/api/channels/{channel_id}/playlist/next")
def update_upcoming_playlist(
    channel_id: str,
    payload: PlaylistUpdateRequest,
    limit: int = Query(default=25, ge=1, le=100),
) -> Dict[str, Any]:
    return apply_playlist_update(channel_id, payload, limit)


def build_playlist_snapshot(channel_id: str, limit: int) -> Dict[str, Any]:
    channel = _require_channel(channel_id)

    try:
        entries, mtime = load_playlist_entries()
    except FileNotFoundError:
        return {
            "channel_id": channel_id,
            "version": 0.0,
            "fetched_at": time.time(),
            "current": None,
            "upcoming": [],
            "total_entries": 0,
            "total_segments": 0,
            "controllable_remaining": 0,
            "limit": limit,
            "state": None,
        }

    segments = build_playlist_segments(entries)
    state = load_playhead_state()

    current_idx = _resolve_current_segment_index(segments, state)
    media_root = channel.get("media_root")
    current_item = (
        _format_segment(segments[current_idx], media_root)
        if current_idx >= 0 and current_idx < len(segments)
        else None
    )

    upcoming_segments = segments[current_idx + 1 :] if current_idx >= 0 else segments
    upcoming_items = [
        _format_segment(segment, media_root)
        for segment in upcoming_segments[:limit]
    ]

    remaining = max(0, len(segments) - (current_idx + 1)) if current_idx >= 0 else len(segments)

    return {
        "channel_id": channel_id,
        "version": mtime,
        "fetched_at": time.time(),
        "current": current_item,
        "upcoming": upcoming_items,
        "total_entries": len(entries),
        "total_segments": len(segments),
        "controllable_remaining": remaining,
        "limit": limit,
        "state": state or None,
    }


def apply_playlist_update(
    channel_id: str, payload: PlaylistUpdateRequest, limit: int
) -> Dict[str, Any]:
    _require_channel(channel_id)

    try:
        entries, mtime = load_playlist_entries()
    except FileNotFoundError as exc:  # pragma: no cover - depends on runtime state
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if payload.version is None:
        raise HTTPException(status_code=400, detail="Missing playlist version.")

    if abs(payload.version - mtime) > 1e-3:
        raise HTTPException(
            status_code=409, detail="Playlist changed; refresh and try again."
        )

    segments = build_playlist_segments(entries)
    if not segments:
        return build_playlist_snapshot(channel_id, limit)

    state = load_playhead_state()
    current_idx = _resolve_current_segment_index(segments, state)
    tail_segments = segments[current_idx + 1 :] if current_idx >= 0 else segments
    window_segments = tail_segments[:limit]
    if not window_segments:
        return build_playlist_snapshot(channel_id, limit)

    allowed_paths = {segment["episode_path"]: segment for segment in window_segments}

    skip_set = set()
    for path in payload.skipped:
        if path not in allowed_paths:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot skip item outside the controllable window: {path}",
            )
        skip_set.add(path)

    ordered_paths: List[str] = []
    for path in payload.desired:
        if path not in allowed_paths or path in skip_set:
            continue
        if path not in ordered_paths:
            ordered_paths.append(path)

    ordered_segments = [allowed_paths[path] for path in ordered_paths]
    ordered_set = set(ordered_paths)

    remaining_segments = [
        segment
        for segment in window_segments
        if segment["episode_path"] not in ordered_set and segment["episode_path"] not in skip_set
    ]

    updated_window = ordered_segments + remaining_segments
    later_segments = tail_segments[len(window_segments) :]

    new_segments: List[Dict[str, Any]] = []
    if current_idx >= 0:
        new_segments.extend(segments[: current_idx + 1])
    new_segments.extend(updated_window)
    new_segments.extend(later_segments)

    flattened = flatten_segments(new_segments)
    new_mtime = write_playlist_entries(flattened)

    # Ensure callers receive fresh data
    snapshot = build_playlist_snapshot(channel_id, limit)
    snapshot["version"] = new_mtime
    return snapshot


def _require_channel(channel_id: str) -> Dict[str, Any]:
    channel = get_channel(channel_id)
    if channel:
        return channel
    raise HTTPException(status_code=404, detail="Channel not found")


def _resolve_current_segment_index(
    segments: List[Dict[str, Any]], state: Dict[str, Any] | None
) -> int:
    if not state:
        return -1
    current_path = state.get("current_path")
    if not current_path:
        return -1
    return find_segment_index_for_entry(segments, current_path)


def _format_segment(segment: Dict[str, Any], media_root: str | None) -> Dict[str, Any]:
    return describe_episode(segment["episode_path"], media_root, segment["index"])


