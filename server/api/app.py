"""
FastAPI application exposing channel configuration management endpoints.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .settings_service import (
    get_channel,
    list_channels,
    normalize_show,
    replace_channel,
    slugify,
)

app = FastAPI(title="Channel Admin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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

    return saved


@app.get("/api/channels/{channel_id}/shows/discover")
def discover_channel_shows(channel_id: str) -> List[Dict[str, Any]]:
    channel = get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    media_root = Path(channel.get("media_root") or "").expanduser()
    if not media_root.exists():
        return []

    shows: List[Dict[str, Any]] = []
    try:
        for child in sorted(media_root.iterdir()):
            if not child.is_dir():
                continue
            rel_path = child.relative_to(media_root)
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


