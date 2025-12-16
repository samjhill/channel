"""
FastAPI application exposing channel configuration management endpoints.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
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
    is_episode_entry,
    load_playhead_state,
    load_playlist_entries,
    resolve_playhead_path,
    resolve_playlist_path,
    save_playhead_state,
    write_playlist_entries,
)
from server.stream import resolve_bumper_block

# Import path normalization if available
try:
    from ..playlist_service import _normalize_path
except ImportError:
    _normalize_path = None

# Cache for computed segments (invalidated when playlist changes)
_segments_cache: Optional[List[Dict[str, Any]]] = None
_segments_playlist_mtime: float = 0.0

app = FastAPI(title="Channel Admin API")

# CORS configuration - restrict origins for security
# Default to localhost for development, can be overridden via CORS_ORIGINS env var
cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:5174,http://localhost:3000")
cors_origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _resolve_hls_dir() -> Path:
    container = Path("/app/hls")
    if container.exists():
        return container
    fallback = REPO_ROOT / "server" / "hls"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


HLS_DIR = _resolve_hls_dir()
def _get_preview_video_path() -> Path:
    """Get preview video path with timestamp to prevent caching."""
    import time
    timestamp = int(time.time())
    return HLS_DIR / f"preview_block_{timestamp}.mp4"
BUMPER_BLOCK_MARKER = "BUMPER_BLOCK"


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
    
    # Try to import psutil for resource monitoring (optional)
    try:
        import psutil
        psutil_available = True
    except ImportError:
        psutil_available = False
    
    health_status = {
        "status": "ok",
        "timestamp": time.time(),
        "checks": {},
        "resources": {},
    }
    
    # Check resource usage (if psutil is available)
    if psutil_available:
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            cpu_percent = process.cpu_percent(interval=0.1)
            
            health_status["resources"] = {
                "memory_mb": round(memory_info.rss / (1024 * 1024), 2),
                "memory_percent": round(process.memory_percent(), 2),
                "cpu_percent": round(cpu_percent, 2),
            }
            
            # Check disk usage for HLS directory
            try:
                hls_dir = _resolve_hls_dir()
                if hls_dir.exists():
                    disk_usage = psutil.disk_usage(str(hls_dir))
                    health_status["resources"]["disk"] = {
                        "total_gb": round(disk_usage.total / (1024**3), 2),
                        "used_gb": round(disk_usage.used / (1024**3), 2),
                        "free_gb": round(disk_usage.free / (1024**3), 2),
                        "percent": round(disk_usage.percent, 2),
                    }
                    
                    # Count HLS segments
                    segment_count = len(list(hls_dir.glob("stream*.ts")))
                    health_status["resources"]["hls_segments"] = segment_count
                    
                    # Warn if disk usage is high
                    if disk_usage.percent > 90:
                        health_status["status"] = "degraded"
                        health_status["checks"]["disk"] = {
                            "status": "warning",
                            "message": f"Disk usage at {disk_usage.percent}%",
                        }
            except Exception as e:
                LOGGER.debug("Failed to check disk usage: %s", e)
            
            # Warn if memory usage is very high
            if process.memory_percent() > 90:
                health_status["status"] = "degraded"
                health_status["checks"]["memory"] = {
                    "status": "warning",
                    "message": f"Memory usage at {process.memory_percent():.1f}%",
                }
        except Exception as e:
            LOGGER.debug("Failed to check resource usage: %s", e)
            health_status["resources"] = {"error": str(e)}
    else:
        # psutil not available, skip resource checks
        health_status["resources"] = {"note": "psutil not available"}
    
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


@app.get("/api/playlist/generation-status")
def get_playlist_generation_status() -> Dict[str, Any]:
    """Get the status of playlist generation process."""
    status = {
        "is_generating": False,
        "playlist_exists": False,
        "playlist_entries": 0,
        "playlist_size": 0,
        "process_info": None,
        "timestamp": time.time(),
    }
    
    # Check if playlist file exists
    try:
        playlist_path = resolve_playlist_path()
        if playlist_path.exists():
            status["playlist_exists"] = True
            status["playlist_size"] = playlist_path.stat().st_size
            
            # Count entries if file has content
            if status["playlist_size"] > 0:
                try:
                    entries, _ = load_playlist_entries()
                    status["playlist_entries"] = len(entries)
                except Exception:
                    # File might be empty or still being written
                    pass
    except Exception as e:
        LOGGER.warning("Failed to check playlist file: %s", e)
    
    # Check if generate_playlist.py is running using pgrep
    try:
        result = subprocess.run(
            ["pgrep", "-f", "generate_playlist.py"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            status["is_generating"] = True
            pids = result.stdout.strip().split('\n')
            if pids and pids[0]:
                try:
                    pid = int(pids[0])
                    # Try to get process info using ps
                    ps_result = subprocess.run(
                        ["ps", "-p", str(pid), "-o", "pid,etime,pcpu,rss"],
                        capture_output=True,
                        text=True,
                        timeout=1,
                    )
                    if ps_result.returncode == 0:
                        lines = ps_result.stdout.strip().split('\n')
                        if len(lines) > 1:
                            parts = lines[1].split()
                            if len(parts) >= 4:
                                status["process_info"] = {
                                    "pid": pid,
                                    "cpu_percent": float(parts[2]) if parts[2] != '-' else 0.0,
                                    "memory_mb": float(parts[3]) / 1024 if parts[3] != '-' else 0.0,
                                    "runtime": parts[1] if parts[1] != '-' else "unknown",
                                }
                except (ValueError, IndexError, subprocess.TimeoutExpired):
                    # If we can't parse ps output, just report that it's running
                    status["process_info"] = {"pid": int(pids[0])}
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        LOGGER.debug("Failed to check for generate_playlist process: %s", e)
    
    return status


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

    # Use segments to find the next episode (consistent with playlist view)
    # This ensures skip button behavior matches what the playlist shows
    segments = build_playlist_segments(entries)
    current_segment_idx = find_segment_index_for_entry(segments, current_path)
    
    if current_segment_idx < 0:
        # Current episode not found in segments, fall back to raw entry search
        LOGGER.warning("Current episode not found in segments, using raw entry search")
        safety_counter = 0
        # Skip markers, but also skip past bumper blocks to find the next episode
        while (not is_episode_entry(entries[next_index])) and safety_counter < len(entries):
            next_index = (next_index + 1) % len(entries)
            safety_counter += 1
        next_path = entries[next_index]
    else:
        # Use segments to find next episode
        next_segment_idx = current_segment_idx + 1
        if next_segment_idx >= len(segments):
            next_segment_idx = 0  # Wrap around
        
        next_segment = segments[next_segment_idx]
        next_path = next_segment["episode_path"]
        
        # Find the raw entry index for this episode path
        try:
            next_index = entries.index(next_path)
        except ValueError:
            # Fallback: search for episode by filename
            next_filename = Path(next_path).name
            for i, entry in enumerate(entries):
                if is_episode_entry(entry) and entry.endswith(next_filename):
                    next_index = i
                    break
            else:
                LOGGER.error("Could not find next episode in raw entries: %s", next_path)
                raise ValueError(f"Next episode not found in entries: {next_path}")
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
        # Ensure messages is always an array
        if "messages" not in config or not isinstance(config.get("messages"), list):
            config["messages"] = []
        # Ensure all required fields have defaults
        config.setdefault("enabled", False)
        config.setdefault("duration_seconds", 5)
        config.setdefault("music_volume", 0.5)
        config.setdefault("probability_between_episodes", 0.0)
        config.setdefault("style", "hbn-cozy")
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


@app.get("/api/logs")
def get_logs(
    container: Optional[str] = Query("tvchannel", description="Docker container name"),
    lines: int = Query(500, ge=1, le=10000, description="Number of lines to fetch"),
    follow: bool = Query(False, description="Whether to follow logs (streaming)"),
) -> Dict[str, Any]:
    """
    Fetch logs from Docker container or log files.
    Returns recent log entries with timestamps.
    """
    import subprocess
    
    try:
        # Try to get logs from Docker container first
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", str(lines), container],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            
            if result.returncode == 0:
                log_lines = result.stdout.splitlines()
                return {
                    "source": "docker",
                    "container": container,
                    "lines": len(log_lines),
                    "logs": log_lines,
                    "timestamp": time.time(),
                }
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # Docker not available or timed out
            pass
        
        # Fallback: Try to read from common log file locations
        log_paths = [
            Path("/app/logs/channel.log"),
            Path("/var/log/channel.log"),
            REPO_ROOT / "logs" / "channel.log",
        ]
        
        for log_path in log_paths:
            if log_path.exists():
                try:
                    with log_path.open("r", encoding="utf-8", errors="ignore") as f:
                        all_lines = f.readlines()
                        # Get last N lines
                        log_lines = [line.rstrip("\n\r") for line in all_lines[-lines:]]
                        return {
                            "source": "file",
                            "path": str(log_path),
                            "lines": len(log_lines),
                            "logs": log_lines,
                            "timestamp": time.time(),
                        }
                except (OSError, IOError) as e:
                    LOGGER.warning("Failed to read log file %s: %s", log_path, e)
                    continue
        
        # If no logs found, return empty result
        return {
            "source": "none",
            "message": "No logs available. Logs may be going to stdout/stderr.",
            "lines": 0,
            "logs": [],
            "timestamp": time.time(),
        }
        
    except Exception as e:
        LOGGER.error("Failed to fetch logs: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to fetch logs: {str(e)}")


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


def _sanitize_concat_path(path: Path) -> str:
    return str(path).replace("'", "'\\''")


def _generate_preview_video(bumpers: List[str]) -> Path:
    """Generate preview video by concatenating bumper videos.
    
    Uses a faster preset and adds timeout to prevent hanging.
    """
    if not bumpers:
        raise ValueError("No bumpers available to preview")
    
    preview_dir = HLS_DIR
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = _get_preview_video_path()
    
    # Check if all bumper files exist
    for bumper_path in bumpers:
        bumper = Path(bumper_path)
        if not bumper.exists():
            raise FileNotFoundError(f"Bumper not found: {bumper}")
    
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(preview_dir), suffix=".txt") as tmp_file:
        concat_file = Path(tmp_file.name)
        for bumper_path in bumpers:
            sanitized = _sanitize_concat_path(Path(bumper_path))
            tmp_file.write(f"file '{sanitized}'\n")
        tmp_file.flush()  # Ensure file is written before closing
    
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",  # Fastest preset for preview
        "-crf",
        "23",  # Slightly lower quality for speed
        "-c:a",
        "copy",  # Copy audio instead of re-encoding
        "-movflags",
        "faststart",
        str(preview_path),
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30.0,  # 30 second timeout
        )
        if result.returncode != 0:
            LOGGER.error("FFmpeg preview generation failed: %s", result.stderr[:500])
            raise RuntimeError(result.stderr.strip() or "ffmpeg failed to build bumper preview")
    except subprocess.TimeoutExpired:
        LOGGER.error("FFmpeg preview generation timed out after 30 seconds")
        raise RuntimeError("Preview generation timed out")
    finally:
        concat_file.unlink(missing_ok=True)
    
    return preview_path


def _find_next_bumper_block(entries: List[str], start_index: int) -> Dict[str, Any]:
    """Find the next bumper block using unified code paths from server.stream.
    
    Uses resolve_bumper_block which has timeout protection and unified logic.
    """
    if not entries:
        raise ValueError("Playlist is empty")
    
    total = len(entries)
    idx = start_index if 0 <= start_index < total else 0
    
    # Search playlist for next bumper block marker
    for offset in range(total):
        current = (idx + offset) % total
        entry = entries[current].strip()
        if entry.upper() != BUMPER_BLOCK_MARKER:
            continue
        
        next_episode_idx = current + 1
        while next_episode_idx < total and not is_episode_entry(entries[next_episode_idx]):
            next_episode_idx += 1
        
        if next_episode_idx >= total:
            continue
        
        # Verify we found a valid episode
        episode_path = entries[next_episode_idx]
        if not episode_path or not os.path.exists(episode_path):
            LOGGER.warning("Preview: Episode path not found or doesn't exist: %s", episode_path)
            continue
        
        from pathlib import Path
        LOGGER.info("Preview: Found next episode at index %d: %s", next_episode_idx, Path(episode_path).name)
        
        # For preview, peek at pre-generated block first (don't consume it)
        # Then fall back to resolve_bumper_block if no pre-generated block exists
        try:
            import threading
            import queue
            import copy
            
            from server.bumper_block import get_generator
            from server.stream import _get_up_next_bumper
            
            generator = get_generator()
            
            # First try to peek at pre-generated block (for preview, don't consume)
            peeked_block = generator.peek_next_pregenerated_block(episode_path=episode_path)
            if not peeked_block:
                # Fallback: try any available block
                peeked_block = generator.peek_next_pregenerated_block(episode_path=None)
            
            if peeked_block:
                # Use peeked block (copy so we don't modify cache)
                block = copy.deepcopy(peeked_block)
                
                # Ensure correct up-next bumper (same logic as in stream.py)
                # Wrap in timeout to prevent blocking on slow bumper generation
                up_next_queue = queue.Queue(maxsize=1)
                
                def get_up_next():
                    try:
                        correct_up_next = _get_up_next_bumper(episode_path)
                        up_next_queue.put(('success', correct_up_next), timeout=1.0)
                    except Exception as e:
                        try:
                            up_next_queue.put(('error', e), timeout=1.0)
                        except queue.Full:
                            pass
                
                up_next_thread = threading.Thread(target=get_up_next, daemon=True)
                up_next_thread.start()
                
                correct_up_next = None
                try:
                    result_type, result_value = up_next_queue.get(timeout=10.0)
                    if result_type == 'success':
                        correct_up_next = result_value
                    else:
                        LOGGER.warning("Preview: Failed to get up-next bumper: %s", result_value)
                except queue.Empty:
                    LOGGER.warning("Preview: Getting up-next bumper timed out after 10s, using existing bumper in block")
                    # Use existing bumper if timeout
                    correct_up_next = None
                
                if correct_up_next and block.bumpers:
                    # Replace up-next bumper if needed
                    for i, bumper_path in enumerate(block.bumpers):
                        if "/bumpers/up_next/" in bumper_path or "/up_next_temp/" in bumper_path:
                            if bumper_path != correct_up_next:
                                LOGGER.info("Preview: Replacing up-next bumper: %s -> %s", 
                                          Path(bumper_path).name, Path(correct_up_next).name)
                                block.bumpers[i] = correct_up_next
                            break
                
                return {
                    "block": block,
                    "block_index": current,
                    "episode_index": next_episode_idx,
                    "episode_path": episode_path,
                }
            
            # No pre-generated block available, use resolve_bumper_block with timeout
            # This will generate on-the-fly but has timeout protection
            result_queue = queue.Queue(maxsize=1)
            
            def resolve_block():
                try:
                    block = resolve_bumper_block(next_episode_idx, entries)
                    result_queue.put(('success', block), timeout=1.0)
                except Exception as e:
                    try:
                        result_queue.put(('error', e), timeout=1.0)
                    except queue.Full:
                        pass
            
            # Start resolution in a thread with timeout
            thread = threading.Thread(target=resolve_block, daemon=True)
            thread.start()
            
            # Wait for result with timeout (25 seconds total for preview)
            try:
                result_type, result_value = result_queue.get(timeout=25.0)
                if result_type == 'success':
                    block = result_value
                else:
                    raise result_value
            except queue.Empty:
                LOGGER.warning("Preview: Bumper block resolution timed out after 25s for episode at index %d", next_episode_idx)
                continue  # Try next bumper block
            
            if block and block.bumpers:
                return {
                    "block": block,
                    "block_index": current,
                    "episode_index": next_episode_idx,
                    "episode_path": episode_path,
                }
        except Exception as e:
            LOGGER.warning("Preview: Failed to resolve bumper block for episode at index %d: %s", next_episode_idx, e, exc_info=True)
            continue  # Try next bumper block
    
    raise ValueError("No upcoming bumper blocks found")


def _build_bumper_preview_payload() -> Dict[str, Any]:
    """Build bumper preview payload from pre-generated block.
    
    Uses unified code paths and has timeout protection to prevent hanging.
    """
    import threading
    import queue
    
    entries, _ = load_playlist_entries()
    
    # Use the same logic as the "next 25" endpoint to find the actual next episode
    # This ensures consistency between the playlist view and the preview
    segments = build_playlist_segments(entries)
    playhead = load_playhead_state(force_reload=True) or {}
    current_idx = _resolve_current_segment_index(segments, playhead)
    
    # Find the next episode segment
    # All segments returned by build_playlist_segments are episode segments
    if not segments:
        LOGGER.warning("Preview: No segments found in playlist - playlist may not be generated yet")
        raise ValueError("No segments found in playlist. Please wait for playlist generation to complete.")
    
    # Get next segment after current
    if current_idx >= 0 and current_idx < len(segments) - 1:
        next_episode_segment = segments[current_idx + 1]
    elif current_idx >= 0 and current_idx == len(segments) - 1:
        # Wrap around to start
        next_episode_segment = segments[0]
    else:
        # No current segment found, use first segment
        next_episode_segment = segments[0]
    
    # Find the bumper block for this episode
    # Use _find_next_bumper_block which searches forward from a start position
    # and finds the next BUMPER_BLOCK_MARKER, then resolves the block for the episode after it
    # Start searching from the beginning of the playlist or from current position
    start_search_idx = 0
    if current_idx >= 0:
        # Try to find the current episode's index in raw entries to start search from there
        current_path = playhead.get("current_path")
        if current_path:
            try:
                current_episode_idx = entries.index(current_path)
                # Start search from a bit before current episode to catch bumper blocks
                start_search_idx = max(0, current_episode_idx - 5)
            except (ValueError, IndexError):
                pass
    
    next_episode_path = next_episode_segment.get("episode_path")
    if not next_episode_path:
        raise ValueError("Next episode segment has no episode_path")
    
    # Find the index of this episode in the raw entries
    try:
        next_episode_idx = entries.index(next_episode_path)
    except ValueError:
        # Try to find by matching the path
        for i, entry in enumerate(entries):
            if is_episode_entry(entry) and entry.endswith(Path(next_episode_path).name):
                next_episode_idx = i
                break
        else:
            raise ValueError(f"Could not find episode in playlist: {next_episode_path}")
    
    LOGGER.info("Preview: Next episode is %s at index %d, searching for bumper block", 
               Path(next_episode_path).name, next_episode_idx)
    
    # Try to find bumper block marker before the episode first
    bumper_block_idx = next_episode_idx - 1
    found_marker = False
    while bumper_block_idx >= 0 and bumper_block_idx >= next_episode_idx - 20:  # Search up to 20 entries back
        if entries[bumper_block_idx].strip().upper() == BUMPER_BLOCK_MARKER:
            found_marker = True
            break
        bumper_block_idx -= 1
    
    # Wrap block finding in timeout protection
    result_queue = queue.Queue(maxsize=1)
    
    def find_block():
        try:
            if found_marker:
                # Found a marker, use _find_next_bumper_block starting from that marker
                # This has its own timeout protection
                info = _find_next_bumper_block(entries, bumper_block_idx)
            else:
                # No marker found, try to use pre-generated block first
                from server.bumper_block import get_generator
                generator = get_generator()
                
                # Try to get pre-generated block for this episode
                peeked_block = generator.peek_next_pregenerated_block(episode_path=next_episode_path)
                if not peeked_block:
                    # Try any available pre-generated block
                    peeked_block = generator.peek_next_pregenerated_block(episode_path=None)
                
                if peeked_block and peeked_block.bumpers:
                    # Use pre-generated block (copy so we don't modify cache)
                    import copy
                    block = copy.deepcopy(peeked_block)
                    LOGGER.info("Preview: Using pre-generated block for episode %s", Path(next_episode_path).name)
                else:
                    # No pre-generated block, try to resolve (with timeout)
                    from server.stream import resolve_bumper_block
                    
                    LOGGER.info("Preview: No pre-generated block found, resolving block directly (may take time)")
                    # Use a shorter timeout for preview - if it takes too long, fail gracefully
                    block = resolve_bumper_block(next_episode_idx, entries)
                    if not block or not block.bumpers:
                        raise ValueError(f"Failed to resolve bumper block for episode at index {next_episode_idx}")
                
                info = {
                    "block": block,
                    "block_index": next_episode_idx - 1,  # Approximate - no actual marker
                    "episode_index": next_episode_idx,
                    "episode_path": next_episode_path,
                }
            
            result_queue.put(('success', info), timeout=1.0)
        except Exception as e:
            try:
                result_queue.put(('error', e), timeout=1.0)
            except queue.Full:
                pass
    
    # Start finding block in a thread
    thread = threading.Thread(target=find_block, daemon=True)
    thread.start()
    
    # Wait for result with timeout (20 seconds - shorter for preview)
    try:
        result_type, result_value = result_queue.get(timeout=20.0)
        if result_type == 'success':
            info = result_value
        else:
            # Log the full error before raising
            error_exc = result_value
            LOGGER.error("Preview: Bumper block finding failed: %s", error_exc, exc_info=True)
            raise error_exc
    except queue.Empty:
        LOGGER.error("Preview: Bumper block finding timed out after 20s")
        raise RuntimeError("Preview generation timed out - bumper block resolution took too long. Try again later when blocks are pre-generated.")
    except ValueError as exc:
        # No bumper blocks found - provide helpful error message
        error_msg = str(exc)
        if "No upcoming bumper blocks" in error_msg or "No segments found" in error_msg:
            LOGGER.warning("Preview: %s - This may be because no bumper blocks have been generated yet", error_msg)
            raise ValueError("No bumper blocks available for preview. Please wait for an episode to start playing so bumper blocks can be pre-generated.")
        raise
    
    block = info["block"]
    
    # Log final bumpers before generating preview video
    LOGGER.info("Preview: Generating preview video with bumpers: %s", 
              [Path(b).name for b in block.bumpers])
    
    # Verify all bumper files exist before attempting to generate preview
    missing_bumpers = []
    for bumper_path in block.bumpers:
        bumper_file = Path(bumper_path)
        if not bumper_file.exists():
            missing_bumpers.append(bumper_path)
            LOGGER.warning("Preview: Missing bumper file: %s (resolved from %s)", bumper_file, bumper_path)
    
    if missing_bumpers:
        error_msg = f"Missing bumper files: {', '.join([Path(b).name for b in missing_bumpers])}"
        LOGGER.error("Preview: %s", error_msg)
        raise FileNotFoundError(error_msg)
    
    # Generate preview video from the pre-generated block (has its own timeout)
    try:
        preview_path = _generate_preview_video(block.bumpers)
        LOGGER.info("Preview: Successfully generated preview video at %s", preview_path)
    except Exception as e:
        LOGGER.error("Preview: Failed to generate preview video: %s", e, exc_info=True)
        raise RuntimeError(f"Failed to generate preview video: {str(e)}") from e
    
    bumpers_summary = [
        {
            "path": path,
            "filename": Path(path).name,
            "type": entry_type(path),
        }
        for path in block.bumpers
    ]
    
    video_url = f"/api/bumper-preview/video?ts={int(time.time())}"
    
    return {
        "video_url": video_url,
        "block_id": block.block_id,
        "music_track": block.music_track,
        "episode_path": info["episode_path"],
        "episode_filename": Path(info["episode_path"]).name,
        "bumpers": bumpers_summary,
        "generated_at": time.time(),
        "preview_path": str(preview_path),
    }


@app.get("/api/bumper-preview/next")
def get_next_bumper_preview() -> Dict[str, Any]:
    """Get next bumper preview with comprehensive timeout protection."""
    import threading
    import queue
    import traceback
    
    result_queue = queue.Queue(maxsize=1)
    error_details = {"traceback": None}
    
    def build_preview():
        try:
            data = _build_bumper_preview_payload()
            result_queue.put(('success', data), timeout=1.0)
        except Exception as e:
            error_details["traceback"] = traceback.format_exc()
            error_details["error"] = str(e)
            try:
                result_queue.put(('error', e), timeout=1.0)
            except queue.Full:
                pass
    
    # Start building preview in a thread
    thread = threading.Thread(target=build_preview, daemon=True)
    thread.start()
    
    # Wait for result with timeout (35 seconds total - slightly longer than internal timeouts)
    try:
        result_type, result_value = result_queue.get(timeout=35.0)
        if result_type == 'success':
            data = result_value
            return {key: value for key, value in data.items() if key != "preview_path"}
        else:
            # Log the full traceback before raising
            if error_details.get("traceback"):
                LOGGER.error("Preview generation failed:\n%s", error_details["traceback"])
            raise result_value
    except queue.Empty:
        LOGGER.error("Preview endpoint timed out after 35s")
        raise HTTPException(status_code=504, detail="Preview generation timed out - please try again")
    except ValueError as exc:
        LOGGER.error("Preview: ValueError - %s", exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        LOGGER.error("Preview: FileNotFoundError - %s", exc)
        raise HTTPException(status_code=404, detail=f"Bumper file not found: {str(exc)}") from exc
    except RuntimeError as exc:
        LOGGER.error("Preview: RuntimeError - %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        error_msg = error_details.get("error", str(exc))
        LOGGER.exception("Failed to build bumper preview: %s", exc)
        if error_details.get("traceback"):
            LOGGER.error("Full traceback:\n%s", error_details["traceback"])
        raise HTTPException(status_code=500, detail=f"Failed to build bumper preview: {error_msg}") from exc


@app.get("/api/bumper-preview/video")
def download_bumper_preview() -> FileResponse:
    # Find the most recent preview video file
    preview_files = sorted(HLS_DIR.glob("preview_block_*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not preview_files:
        raise HTTPException(status_code=404, detail="No bumper preview available")
    
    preview_path = preview_files[0]
    return FileResponse(
        preview_path,
        media_type="video/mp4",
        filename="bumper_preview.mp4",
    )
