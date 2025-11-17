"""
FastAPI application exposing channel configuration management endpoints.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

LOGGER = logging.getLogger(__name__)

from .media_control import restart_media_server
from .settings_service import (
    get_channel,
    list_channels,
    normalize_show,
    replace_channel,
    slugify,
)

# Import sassy config helpers
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from scripts.bumpers.render_sassy_card import (
    resolve_sassy_config_path,
    load_sassy_config,
)
from server.services import weather_service
from ..playlist_service import (
    build_playlist_segments,
    describe_episode,
    entry_type,
    find_segment_index_for_entry,
    flatten_segments,
    load_playhead_state,
    load_playlist_entries,
    resolve_playhead_path,
    resolve_playlist_path,
    save_playhead_state,
    write_playlist_entries,
)

# Import path normalization if available
try:
    from ..playlist_service import _normalize_path
except ImportError:
    _normalize_path = None

# Cache for computed segments (invalidated when playlist changes)
_segments_cache: Optional[List[Dict[str, Any]]] = None
_segments_playlist_mtime: float = 0.0

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
def health_check() -> Dict[str, Any]:
    """Health check endpoint that verifies streaming processes are running."""
    import subprocess
    
    health_status = {
        "status": "ok",
        "timestamp": time.time(),
        "checks": {},
    }
    
    # Check if playlist file exists and is recent (updated in last 5 minutes)
    try:
        entries, mtime = load_playlist_entries()
        playlist_age = time.time() - mtime
        health_status["checks"]["playlist"] = {
            "status": "ok" if playlist_age < 300 else "stale",
            "age_seconds": playlist_age,
            "entries": len(entries),
        }
        if playlist_age > 300:
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["checks"]["playlist"] = {
            "status": "error",
            "error": str(e),
        }
        health_status["status"] = "error"
    
    # Check if playhead file exists and is recent (updated in last 2 minutes)
    try:
        playhead = load_playhead_state()
        if playhead:
            updated_at = playhead.get("updated_at", 0)
            playhead_age = time.time() - updated_at if updated_at > 0 else 999999
            health_status["checks"]["playhead"] = {
                "status": "ok" if playhead_age < 120 else "stale",
                "age_seconds": playhead_age,
                "current_path": playhead.get("current_path"),
            }
            if playhead_age > 120:
                health_status["status"] = "degraded"
        else:
            health_status["checks"]["playhead"] = {"status": "ok", "note": "no playhead"}
    except Exception as e:
        health_status["checks"]["playhead"] = {
            "status": "error",
            "error": str(e),
        }
        health_status["status"] = "degraded"
    
    # Check if processes are running (if we can access Docker)
    try:
        result = subprocess.run(
            ["docker", "exec", "tvchannel", "pgrep", "-f", "process_monitor.py"],
            capture_output=True,
            timeout=2,
        )
        if result.returncode == 0:
            health_status["checks"]["process_monitor"] = {"status": "ok"}
        else:
            health_status["checks"]["process_monitor"] = {"status": "not_running"}
            health_status["status"] = "error"
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        # Docker not available or can't check - don't fail health check
        health_status["checks"]["process_monitor"] = {"status": "unknown"}
    
    return health_status


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

    # Attempt to restart the media server to apply changes
    restart_success = restart_media_server()
    if not restart_success:
        # Log warning but don't fail the request - settings are saved
        import logging

        logging.warning(
            "Channel settings saved but server restart/playlist regeneration failed"
        )

    return saved


@app.get("/api/channels/{channel_id}/shows/discover")
def discover_channel_shows(
    channel_id: str,
    media_root: Optional[str] = Query(
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
        # Collect directories first, then sort once
        dirs = [child for child in base_path.iterdir() if child.is_dir()]
        # Sort only if we have directories to process
        if dirs:
            dirs.sort(key=lambda p: p.name.lower())

        for child in dirs:
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


@app.post("/api/channels/{channel_id}/playlist/skip-current")
def skip_current_episode(channel_id: str) -> Dict[str, Any]:
    """Skip to the end of the currently playing episode by advancing the playhead."""
    _require_channel(channel_id)

    # CRITICAL: Sync playlist and playhead from container to host FIRST
    # The streamer uses the container playlist, so we need to use the same one
    try:
        import subprocess

        playlist_path = resolve_playlist_path()
        # Sync playlist from container to host
        result = subprocess.run(
            ["docker", "cp", "tvchannel:/app/hls/playlist.txt", str(playlist_path)],
            capture_output=True,
            timeout=2,
        )
        if result.returncode == 0:
            LOGGER.debug("Synced playlist from container to host")
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        LOGGER.warning("Could not sync playlist from container: %s", e)

    try:
        entries, mtime = load_playlist_entries()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Playlist not found") from None

    # CRITICAL: Sync playhead from container to host, so we skip from what's actually playing
    # The streamer writes to the container playhead, so that's the source of truth
    try:
        import subprocess

        playhead_path = resolve_playhead_path()
        # Sync from container to host (container is source of truth for what's playing)
        result = subprocess.run(
            ["docker", "cp", "tvchannel:/app/hls/playhead.json", str(playhead_path)],
            capture_output=True,
            timeout=2,
        )
        if result.returncode == 0:
            LOGGER.debug("Synced playhead from container to host")
        else:
            LOGGER.warning(
                "Failed to sync playhead from container: %s",
                result.stderr.decode() if result.stderr else "Unknown error",
            )
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        LOGGER.warning("Could not sync playhead from container: %s", e)

    # Now load the synced playhead state
    state = load_playhead_state(force_reload=True)
    if not state or not state.get("current_path"):
        raise HTTPException(status_code=400, detail="No current episode to skip")

    current_path = state.get("current_path")
    current_index = state.get("current_index", -1)

    LOGGER.debug("Skip request - current_path=%s, current_index=%s", current_path, current_index)

    # Find the current item in the playlist (using normalized path comparison)
    try:
        # Normalize the current path for comparison
        normalized_current = (
            _normalize_path(current_path) if _normalize_path else current_path
        )

        if current_index >= 0 and current_index < len(entries):
            # Verify the index matches the path (with normalization)
            normalized_entry = (
                _normalize_path(entries[current_index])
                if _normalize_path
                else entries[current_index]
            )
            if normalized_entry == normalized_current:
                next_index = current_index + 1
            else:
                # Index might be stale, search for the path using normalized comparison
                next_index = -1
                for idx, entry in enumerate(entries):
                    normalized_entry = (
                        _normalize_path(entry) if _normalize_path else entry
                    )
                    if normalized_entry == normalized_current:
                        next_index = idx + 1
                        break
        else:
            # Index is invalid, search for the path using normalized comparison
            next_index = -1
            for idx, entry in enumerate(entries):
                normalized_entry = _normalize_path(entry) if _normalize_path else entry
                if normalized_entry == normalized_current:
                    next_index = idx + 1
                    break

        if next_index == -1:
            LOGGER.error(
                "Current episode not found in playlist. current_path=%s, playlist_length=%d",
                current_path,
                len(entries),
            )
            raise ValueError("Current episode not found in playlist")
        else:
            LOGGER.debug(
                "Found current episode, calculated next_index=%d",
                next_index,
            )
    except ValueError as e:
        LOGGER.error("ValueError during skip: %s", e)
        raise HTTPException(
            status_code=400, detail="Current episode not found in playlist"
        ) from None

    # If we're at the end, wrap around
    if next_index >= len(entries):
        next_index = 0
        LOGGER.debug("Wrapped around to index 0")

    # Advance to the next actual media entry (skip markers like BUMPER_BLOCK / WEATHER_BUMPER)
    def _is_marker(entry: str) -> bool:
        normalized = entry.strip().upper()
        return normalized in {"BUMPER_BLOCK", "WEATHER_BUMPER"}

    safety_counter = 0
    while _is_marker(entries[next_index]) and safety_counter < len(entries):
        next_index = (next_index + 1) % len(entries)
        safety_counter += 1

    next_path = entries[next_index]
    new_state = {
        "current_path": next_path,
        "current_index": next_index,
        "playlist_mtime": mtime,
        "playlist_path": str(resolve_playlist_path()),
        "entry_type": entry_type(next_path),
    }
    save_playhead_state(new_state)

    LOGGER.info("Updated playhead to next_path=%s, next_index=%d", next_path, next_index)

    # Force sync the playhead file to the container if running in Docker
    # This ensures the streamer sees the update immediately
    sync_success = False
    try:
        import subprocess

        playhead_path = resolve_playhead_path()
        # Try to copy to container (this will fail if not in Docker, which is fine)
        result = subprocess.run(
            ["docker", "cp", str(playhead_path), "tvchannel:/app/hls/playhead.json"],
            capture_output=True,
            timeout=3,
        )
        if result.returncode == 0:
            sync_success = True
            LOGGER.info(
                "Successfully synced playhead to container: %s (index %d)",
                next_path,
                next_index,
            )
        else:
            error_msg = result.stderr.decode() if result.stderr else "Unknown error"
            LOGGER.error("Failed to sync playhead to container: %s", error_msg)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to sync playhead to streamer: {error_msg}",
            )
    except HTTPException:
        raise
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        # Docker not available or copy failed
        error_msg = str(e)
        LOGGER.error("Could not sync playhead to container: %s", error_msg)
        raise HTTPException(
            status_code=500, detail=f"Failed to sync playhead to streamer: {error_msg}"
        )

    # Wait for the streamer to actually jump to the new episode (synchronous)
    # Poll the container playhead to confirm the skip happened
    # Reduced wait time: streamer checks playhead every 0.5s, so should detect within 1-2s
    max_wait_time = 5.0  # Maximum time to wait for skip (seconds) - reduced from 10s
    poll_interval = (
        0.2  # Check every 0.2 seconds for faster confirmation - reduced from 0.5s
    )
    start_time = time.time()
    skip_confirmed = False

    # Normalize the original and target paths for comparison
    if _normalize_path:
        normalized_current = _normalize_path(current_path)
        normalized_next = _normalize_path(next_path)
    else:
        normalized_current = current_path
        normalized_next = next_path

    LOGGER.debug(
        "Waiting for streamer to jump from %s to %s...",
        current_path,
        next_path,
    )

    while (time.time() - start_time) < max_wait_time:
        try:
            # Check container playhead to see if streamer has jumped
            result = subprocess.run(
                ["docker", "exec", "tvchannel", "cat", "/app/hls/playhead.json"],
                capture_output=True,
                timeout=1,  # Reduced timeout from 2s to 1s for faster polling
            )
            if result.returncode == 0:
                import json

                container_state = json.loads(result.stdout.decode())
                container_path = container_state.get("current_path")
                container_updated_at = container_state.get("updated_at", 0.0)

                # Normalize paths for comparison
                if _normalize_path:
                    normalized_container = (
                        _normalize_path(container_path) if container_path else None
                    )
                else:
                    normalized_container = container_path

                # Check if playhead has changed from the original (skip happened)
                # We accept if it matches the target OR if it's different from the original
                # (the streamer might have advanced further)
                paths_match_target = (
                    normalized_container == normalized_next
                    if normalized_container
                    else False
                )
                path_changed_from_original = (
                    normalized_container != normalized_current
                    if normalized_container
                    else False
                )

                # More lenient: check if it was updated recently (within last 15 seconds) to ensure it's a fresh update
                # Increased window to account for Docker sync delays
                current_time = time.time()
                recently_updated = (
                    container_updated_at > 0
                    and (current_time - container_updated_at) < 15.0
                )

                if paths_match_target and recently_updated:
                    skip_confirmed = True
                    elapsed = time.time() - start_time
                    LOGGER.info(
                        "Skip confirmed! Streamer jumped to %s (took %.2fs, updated %.2fs ago)",
                        next_path,
                        elapsed,
                        current_time - container_updated_at,
                    )
                    break
                elif path_changed_from_original and recently_updated:
                    # Playhead changed from original and was recently updated - skip happened
                    # This is sufficient confirmation - streamer detected the skip
                    skip_confirmed = True
                    elapsed = time.time() - start_time
                    LOGGER.info(
                        "Skip confirmed! Streamer jumped to %s (took %.2fs, different from original, updated %.2fs ago)",
                        container_path,
                        elapsed,
                        current_time - container_updated_at,
                    )
                    break
        except Exception as e:
            LOGGER.error("Error checking container playhead: %s", e)

        time.sleep(poll_interval)

    if not skip_confirmed:
        error_msg = f"Skip command sent but streamer did not jump within {max_wait_time} seconds. Current playhead may still be at {current_path}"
        LOGGER.error("Skip timeout: %s", error_msg)
        raise HTTPException(status_code=504, detail=error_msg)

    # Return updated snapshot
    return build_playlist_snapshot(channel_id, 25)


class SassyConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    duration_seconds: Optional[float] = None
    music_volume: Optional[float] = None
    probability_between_episodes: Optional[float] = None
    style: Optional[str] = None
    messages: Optional[List[str]] = None


class WeatherConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    location: Optional[Dict[str, Any]] = None
    units: Optional[str] = None
    duration_seconds: Optional[float] = None
    cache_ttl_minutes: Optional[float] = None
    probability_between_episodes: Optional[float] = None
    music_volume: Optional[float] = None
    api_key: Optional[str] = None  # Special field for setting API key via UI


@app.get("/api/bumpers/sassy")
def get_sassy_config() -> Dict[str, Any]:
    """Get the current sassy messages configuration."""
    try:
        config = load_sassy_config()
        return config
    except Exception as e:
        LOGGER.error("Failed to load sassy config: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to load config: {str(e)}")


@app.put("/api/bumpers/sassy")
def update_sassy_config(update: SassyConfigUpdate) -> Dict[str, Any]:
    """Update the sassy messages configuration."""
    try:
        config_path = resolve_sassy_config_path()
        
        # Load current config
        current_config = load_sassy_config()
        
        # Apply updates
        if update.enabled is not None:
            current_config["enabled"] = update.enabled
        if update.duration_seconds is not None:
            current_config["duration_seconds"] = update.duration_seconds
        if update.music_volume is not None:
            current_config["music_volume"] = max(0.0, min(1.0, update.music_volume))
        if update.probability_between_episodes is not None:
            current_config["probability_between_episodes"] = max(
                0.0, min(1.0, update.probability_between_episodes)
            )
        if update.style is not None:
            current_config["style"] = update.style
        if update.messages is not None:
            # Filter out empty messages
            current_config["messages"] = [msg for msg in update.messages if msg.strip()]
        
        # Ensure config directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write updated config
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(current_config, f, indent=2, ensure_ascii=False)
        
        LOGGER.info("Updated sassy config at %s", config_path)
        return current_config
    except Exception as e:
        LOGGER.error("Failed to update sassy config: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to update config: {str(e)}")


@app.get("/api/bumpers/weather")
def get_weather_config() -> Dict[str, Any]:
    """Get the current weather bumper configuration."""
    try:
        import os
        
        config = weather_service.load_weather_config()
        api_var = config.get("api_key_env_var", "HBN_WEATHER_API_KEY")
        api_key_present = bool(
            os.getenv(api_var)
            or weather_service.load_stored_api_key()
            or config.get("api_key")
        )
        config["api_key_set"] = api_key_present
        config["api_key"] = None  # Never expose the actual key
        return config
    except Exception as e:
        LOGGER.error("Failed to load weather config: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to load config: {str(e)}")


@app.put("/api/bumpers/weather")
def update_weather_config(update: WeatherConfigUpdate) -> Dict[str, Any]:
    """Update the weather bumper configuration."""
    try:
        import os
        
        # Load current config
        current_config = weather_service.load_weather_config()
        
        # Apply updates
        if update.enabled is not None:
            current_config["enabled"] = update.enabled
        if update.location is not None:
            current_config["location"] = {**current_config.get("location", {}), **update.location}
        if update.units is not None:
            if update.units in ["imperial", "metric"]:
                current_config["units"] = update.units
        if update.duration_seconds is not None:
            current_config["duration_seconds"] = max(1.0, min(30.0, update.duration_seconds))
        if update.cache_ttl_minutes is not None:
            current_config["cache_ttl_minutes"] = max(1.0, min(60.0, update.cache_ttl_minutes))
        if update.probability_between_episodes is not None:
            current_config["probability_between_episodes"] = max(
                0.0, min(1.0, update.probability_between_episodes)
            )
        if update.music_volume is not None:
            current_config["music_volume"] = max(0.0, min(1.0, update.music_volume))
        
        # Handle API key specially - set as environment variable
        if update.api_key is not None and update.api_key.strip():
            api_key = update.api_key.strip()
            api_var = current_config.get("api_key_env_var", "HBN_WEATHER_API_KEY")
            # Set environment variable (will persist for current process, but user should set in Docker/system env)
            os.environ[api_var] = api_key
            LOGGER.info("API key set via UI (for current process). For persistence, set %s as environment variable.", api_var)
            weather_service.store_api_key(api_key)
        
        # Ensure config directory exists
        weather_service.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        # Write updated config (without API key - it should be in env var)
        config_to_save = {**current_config}
        if "api_key" in config_to_save:
            del config_to_save["api_key"]  # Don't save API key in config file
        
        with open(weather_service.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config_to_save, f, indent=2, ensure_ascii=False)
        
        LOGGER.info("Updated weather config at %s", weather_service.CONFIG_PATH)
        
        # Return updated config (without exposing API key)
        return get_weather_config()
    except Exception as e:
        LOGGER.error("Failed to update weather config: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to update config: {str(e)}")


def build_playlist_snapshot(channel_id: str, limit: int) -> Dict[str, Any]:
    global _segments_cache, _segments_playlist_mtime

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

    # Use cached segments if playlist hasn't changed
    if _segments_cache is None or abs(mtime - _segments_playlist_mtime) > 0.001:
        segments = build_playlist_segments(entries)
        _segments_cache = segments
        _segments_playlist_mtime = mtime
    else:
        segments = _segments_cache

    # Sync playhead from container before loading (for accurate current episode display)
    try:
        import subprocess

        playhead_path = resolve_playhead_path()
        result = subprocess.run(
            ["docker", "cp", "tvchannel:/app/hls/playhead.json", str(playhead_path)],
            capture_output=True,
            timeout=1,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass

    state = load_playhead_state(force_reload=True)

    current_idx = _resolve_current_segment_index(segments, state)
    media_root = channel.get("media_root")
    current_item = (
        _format_segment(segments[current_idx], media_root)
        if current_idx >= 0 and current_idx < len(segments)
        else None
    )

    upcoming_segments = segments[current_idx + 1 :] if current_idx >= 0 else segments
    upcoming_items = [
        _format_segment(segment, media_root) for segment in upcoming_segments[:limit]
    ]

    remaining = (
        max(0, len(segments) - (current_idx + 1)) if current_idx >= 0 else len(segments)
    )

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
    global _segments_cache, _segments_playlist_mtime

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

    # Use cached segments if available and valid
    if _segments_cache is not None and abs(mtime - _segments_playlist_mtime) < 0.001:
        segments = _segments_cache
    else:
        segments = build_playlist_segments(entries)
        _segments_cache = segments
        _segments_playlist_mtime = mtime
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
        if segment["episode_path"] not in ordered_set
        and segment["episode_path"] not in skip_set
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

    # Invalidate segments cache after write
    _segments_cache = None
    _segments_playlist_mtime = 0.0

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
    segments: List[Dict[str, Any]], state: Optional[Dict[str, Any]]
) -> int:
    if not state:
        return -1
    current_path = state.get("current_path")
    if not current_path:
        return -1
    return find_segment_index_for_entry(segments, current_path)


def _format_segment(
    segment: Dict[str, Any], media_root: Optional[str]
) -> Dict[str, Any]:
    return describe_episode(segment["episode_path"], media_root, segment["index"])
