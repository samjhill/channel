#!/usr/bin/env python3

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional

LOGGER = logging.getLogger(__name__)

try:
    from playlist_service import (
        entry_type,
        is_episode_entry,
        load_playhead_state,
        load_playlist_entries,
        mark_episode_watched,
        resolve_playhead_path,
        resolve_playlist_path,
        save_playhead_state,
    )

    # Try to import _normalize_path if available (for path comparison)
    try:
        from playlist_service import _normalize_path
    except ImportError:
        _normalize_path = None
except ImportError:
    # Fallback for local development outside Docker
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from server.playlist_service import (
        entry_type,
        is_episode_entry,
        load_playhead_state,
        load_playlist_entries,
        mark_episode_watched,
        resolve_playhead_path,
        resolve_playlist_path,
        save_playhead_state,
    )

    # Try to import _normalize_path if available
    try:
        from server.playlist_service import _normalize_path
    except ImportError:
        _normalize_path = None

PLAYLIST = str(resolve_playlist_path())
OUTPUT = "/app/hls/stream.m3u8"
DEFAULT_ASSETS_ROOT = "/app/assets"
DEFAULT_BUG_IMAGE = "branding/hbn_logo_bug.png"


def resolve_assets_root() -> str:
    override = os.environ.get("HBN_ASSETS_ROOT")
    if override:
        return override

    if os.path.isdir(DEFAULT_ASSETS_ROOT):
        return DEFAULT_ASSETS_ROOT

    repo_guess = os.path.abspath(
        os.path.join(Path(__file__).resolve().parent.parent, "assets")
    )
    if os.path.isdir(repo_guess):
        return repo_guess

    return DEFAULT_ASSETS_ROOT


def get_float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def get_int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return int(default)


ASSETS_ROOT = resolve_assets_root()
BUG_IMAGE_PATH = os.environ.get(
    "HBN_BUG_PATH", os.path.join(ASSETS_ROOT, DEFAULT_BUG_IMAGE)
)
BUG_ALPHA = get_float_env("HBN_BUG_ALPHA", 0.8)
BUG_HEIGHT_FRACTION = get_float_env("HBN_BUG_HEIGHT_FRACTION", 0.12)
BUG_MARGIN = get_int_env("HBN_BUG_MARGIN", 40)
BUG_POSITION = os.environ.get("HBN_BUG_POSITION", "top-right").lower()

# Cache for video height probing (expensive operation)
# Limited to 1000 entries to prevent memory leaks
_video_height_cache: Dict[str, Optional[int]] = {}
_MAX_VIDEO_HEIGHT_CACHE_SIZE = 1000


WEATHER_BUMPER_MARKER = "WEATHER_BUMPER"
BUMPER_BLOCK_MARKER = "BUMPER_BLOCK"

# Temporary directory for JIT-rendered weather bumpers
_weather_bumper_temp_dir: Optional[Path] = None


def _get_weather_temp_dir() -> Path:
    """Get or create the temp directory for weather bumpers."""
    global _weather_bumper_temp_dir
    if _weather_bumper_temp_dir is None:
        _weather_bumper_temp_dir = Path(tempfile.mkdtemp(prefix="weather_runtime_"))
    return _weather_bumper_temp_dir


def is_weather_bumper(entry: str) -> bool:
    """Check if an entry is a weather bumper marker."""
    return entry.strip() == WEATHER_BUMPER_MARKER


def is_bumper_block(entry: str) -> bool:
    """Check if an entry is a bumper block marker."""
    return entry.strip() == BUMPER_BLOCK_MARKER


def _resolve_bumper_block(current_index: int, files: List[str]) -> Optional[Any]:
    """Resolve a bumper block marker to an actual bumper block."""
    try:
        from server.bumper_block import get_generator
        from server.generate_playlist import (
            SASSY_CARDS, NETWORK_BUMPERS, load_weather_config, WEATHER_BUMPER_MARKER,
            find_existing_bumper, extract_episode_metadata
        )
        import random
        
        generator = get_generator()
        
        # Determine what bumpers should be in this block
        # Look ahead to find the next episode
        next_episode_index = current_index + 1
        while next_episode_index < len(files) and (
            is_bumper_block(files[next_episode_index]) or 
            is_weather_bumper(files[next_episode_index])
        ):
            next_episode_index += 1
        
        up_next_bumper = None
        if next_episode_index < len(files):
            next_episode = files[next_episode_index]
            if os.path.exists(next_episode):
                # Extract show info from episode path
                from server.generate_playlist import infer_show_title_from_path
                show_label = infer_show_title_from_path(next_episode)
                metadata = extract_episode_metadata(next_episode)
                up_next_bumper = find_existing_bumper(show_label, metadata)
        
        sassy_card = SASSY_CARDS.draw_card()
        network_bumper = NETWORK_BUMPERS.draw_bumper()
        
        weather_bumper = None
        try:
            weather_cfg = load_weather_config()
            if weather_cfg.get("enabled", False):
                weather_prob = weather_cfg.get("probability_between_episodes", 0.0)
                if weather_prob > 0 and random.random() <= weather_prob:
                    # Render weather bumper JIT
                    weather_path = _render_weather_bumper_jit()
                    if weather_path:
                        weather_bumper = weather_path
        except Exception:
            pass
        
        # Generate the block
        block = generator.generate_block(
            up_next_bumper=up_next_bumper,
            sassy_card=sassy_card,
            network_bumper=network_bumper,
            weather_bumper=weather_bumper,
        )
        
        return block
    except Exception as e:
        LOGGER.error(f"Failed to resolve bumper block: {e}")
        return None


def _queue_next_bumper_block(current_index: int, files: List[str]) -> None:
    """Queue the next bumper block for pre-generation."""
    try:
        from server.bumper_block import get_generator
        from server.generate_playlist import (
            SASSY_CARDS, NETWORK_BUMPERS, load_weather_config,
            find_existing_bumper, extract_episode_metadata
        )
        import random
        
        # Find the next episode after current
        next_episode_index = current_index + 1
        while next_episode_index < len(files) and (
            is_bumper_block(files[next_episode_index]) or 
            is_weather_bumper(files[next_episode_index])
        ):
            next_episode_index += 1
        
        if next_episode_index >= len(files):
            return
        
        # Look ahead to find episode after the next bumper block
        episode_after_block = next_episode_index + 1
        while episode_after_block < len(files) and (
            is_bumper_block(files[episode_after_block]) or 
            is_weather_bumper(files[episode_after_block])
        ):
            episode_after_block += 1
        
        if episode_after_block >= len(files):
            return
        
        next_episode = files[episode_after_block]
        if not os.path.exists(next_episode):
            return
        
        # Determine bumpers for next block
        from server.generate_playlist import infer_show_title_from_path
        show_label = infer_show_title_from_path(next_episode)
        metadata = extract_episode_metadata(next_episode)
        up_next_bumper = find_existing_bumper(show_label, metadata)
        
        # Queue for pre-generation
        generator = get_generator()
        generator.queue_pregen({
            "up_next_bumper": up_next_bumper,
            "sassy_card": None,  # Will be drawn when generating
            "network_bumper": None,  # Will be drawn when generating
            "weather_bumper": None,  # Will be determined when generating
        })
    except Exception as e:
        LOGGER.debug(f"Failed to queue next bumper block: {e}")


def _render_weather_bumper_jit() -> Optional[str]:
    """Render a weather bumper just-in-time for playback."""
    try:
        from scripts.bumpers.render_weather_bumper import render_weather_bumper
    except ImportError:
        import sys
        repo_root = Path(__file__).resolve().parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from scripts.bumpers.render_weather_bumper import render_weather_bumper
    
    temp_dir = _get_weather_temp_dir()
    out_path = temp_dir / f"weather_{int(time.time())}.mp4"
    
    success = render_weather_bumper(str(out_path))
    if success and out_path.exists():
        return str(out_path)
    return None


def load_playlist():
    entries, mtime = load_playlist_entries()
    return [entry for entry in entries if entry], mtime


def format_number(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def overlay_position_expr(position: str, margin: int) -> tuple[str, str]:
    margin_str = str(margin)
    mapping = {
        "top-left": (margin_str, margin_str),
        "top-right": (f"main_w-overlay_w-{margin_str}", margin_str),
        "bottom-left": (margin_str, f"main_h-overlay_h-{margin_str}"),
        "bottom-right": (
            f"main_w-overlay_w-{margin_str}",
            f"main_h-overlay_h-{margin_str}",
        ),
    }
    return mapping.get(position, mapping["top-right"])


def probe_video_height(src: str) -> Optional[int]:
    """Probe video height with caching to avoid repeated ffprobe calls."""
    # Check cache first
    if src in _video_height_cache:
        return _video_height_cache[src]

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=height",
                "-of",
                "csv=p=0",
                src,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,  # Add timeout to prevent hanging on corrupted files
        )
        height_str = result.stdout.strip()
        height = int(height_str) if height_str else None
    except (subprocess.CalledProcessError, ValueError, subprocess.TimeoutExpired):
        height = None

    # Cache the result (even if None to avoid repeated failures)
    # Limit cache size to prevent memory leaks
    if len(_video_height_cache) >= _MAX_VIDEO_HEIGHT_CACHE_SIZE:
        # Remove oldest 20% of entries (simple FIFO-style cleanup)
        keys_to_remove = list(_video_height_cache.keys())[
            : _MAX_VIDEO_HEIGHT_CACHE_SIZE // 5
        ]
        for key in keys_to_remove:
            del _video_height_cache[key]

    _video_height_cache[src] = height
    return height


def build_overlay_args(video_height: Optional[int]):
    if not os.path.isfile(BUG_IMAGE_PATH):
        return [], False

    alpha = format_number(BUG_ALPHA)
    x_expr, y_expr = overlay_position_expr(BUG_POSITION, BUG_MARGIN)

    stages = [
        f"[1]format=rgba,colorchannelmixer=aa={alpha}[logo_base]",
    ]

    logo_stream = "[logo_base]"
    if video_height:
        target_height = max(2, int(video_height * BUG_HEIGHT_FRACTION))
        if target_height % 2:
            target_height += 1

        stages.append(f"{logo_stream}scale=-1:{target_height}[logo_scaled]")
        logo_stream = "[logo_scaled]"

    stages.append(f"[0]{logo_stream}overlay=x={x_expr}:y={y_expr}:shortest=1[vout]")
    filter_expr = ";".join(stages)

    args = [
        "-loop",
        "1",
        "-i",
        BUG_IMAGE_PATH,
        "-filter_complex",
        filter_expr,
        "-map",
        "[vout]",
        "-map",
        "0:a?",
    ]
    return args, True


def stream_file(
    src: str, expected_index: int = -1, playlist_mtime: float = 0.0
) -> bool:
    """
    Stream a video file to HLS output.
    Periodically checks if playhead has been updated externally (skip button).
    If skip is detected, interrupts the stream and returns False.
    Returns True if streaming completed successfully, False if interrupted or failed.
    """
    # Validate file exists before attempting to stream
    if not os.path.exists(src):
        LOGGER.error("File not found: %s", src)
        return False

    if not os.path.isfile(src):
        LOGGER.error("Path is not a file: %s", src)
        return False

    LOGGER.info("Streaming: %s (index %d)", src, expected_index)
    
    # CRITICAL: When switching files, we need to ensure clients get fresh content
    # Check if we're switching to a different file (not continuing the same one)
    is_file_switch = True
    try:
        if os.path.exists(OUTPUT):
            # Read last few lines of playlist to see what was last streamed
            with open(OUTPUT, 'r') as f:
                lines = f.readlines()
                # If playlist has segments, we're switching files
                if any('stream' in line and '.ts' in line for line in lines[-20:]):
                    is_file_switch = True
    except Exception:
        pass
    
    video_height = probe_video_height(src)
    overlay_args, has_overlay = build_overlay_args(video_height)
    cmd = [
        "ffmpeg",
        "-re",
        "-i",
        src,
    ]
    cmd += overlay_args
    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-maxrate",
        "3000k",
        "-bufsize",
        "9000k",  # Increased from 6000k to 9000k (3x maxrate)
        # Larger buffer helps maintain consistent bitrate and reduces stalls
        "-g",
        "60",  # GOP size matches segment duration (6s * 10fps typical = 60 frames)
        "-sc_threshold",
        "0",  # Disable scene change detection for consistent keyframes
        "-force_key_frames",
        "expr:gte(t,n_forced*6)",  # Force keyframe every 6 seconds (segment duration)
        "-keyint_min",
        "60",  # Minimum keyframe interval (matches GOP size)
        "-c:a",
        "aac",
        "-ac",
        "2",
        "-ar",
        "48000",
        "-b:a",
        "128k",
        "-f",
        "hls",
        "-hls_time",
        "6",
        "-hls_list_size",
        "50",  # Increased from 30 to 50 segments (300s buffer vs 180s)
        # This gives clients more segments to buffer, reducing stalls
        "-hls_flags",
        "delete_segments+append_list+omit_endlist+discont_start+program_date_time",
        # Added program_date_time for better synchronization
        "-hls_segment_type",
        "mpegts",
        "-hls_segment_filename",
        "/app/hls/stream%04d.ts",
        OUTPUT,
    ]

    # Start FFmpeg as a subprocess so we can monitor it
    # Log the command for debugging (truncate long filter expressions)
    cmd_str = " ".join(cmd[:10]) + " ... [filter_complex] ... " + " ".join(cmd[-5:])
    LOGGER.debug("FFmpeg command: %s", cmd_str)
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Check for playhead updates every 0.5 seconds while streaming
    # This ensures skip commands are detected quickly
    check_interval = 0.5
    last_check = time.time()

    while process.poll() is None:
        # Check if process is still running
        time.sleep(0.5)  # Small sleep to avoid busy-waiting

        # Periodically check if playhead was updated externally (skip button)
        current_time = time.time()
        if current_time - last_check >= check_interval:
            last_check = current_time

            # Force reload playhead state to ensure we see the latest update
            playhead_state = load_playhead_state(force_reload=True)
            if playhead_state and playhead_state.get("current_path"):
                playhead_path = playhead_state.get("current_path")
                playhead_index = playhead_state.get("current_index", -1)
                playhead_mtime = playhead_state.get("playlist_mtime", 0.0)

                # Normalize paths for comparison (handles container vs host path differences)
                if _normalize_path:
                    normalized_playhead = _normalize_path(playhead_path)
                    normalized_src = _normalize_path(src)
                    paths_differ = normalized_playhead != normalized_src
                else:
                    # Fallback: direct comparison
                    paths_differ = playhead_path != src

                # Debug logging
                if paths_differ:
                    LOGGER.debug(
                        "Playhead check - src=%s, playhead=%s, normalized_src=%s, normalized_playhead=%s, paths_differ=%s, mtime_match=%s",
                        src,
                        playhead_path,
                        normalized_src if _normalize_path else "N/A",
                        normalized_playhead if _normalize_path else "N/A",
                        paths_differ,
                        abs(playhead_mtime - playlist_mtime) < 0.001,
                    )

                # If playhead points to a different file, skip was triggered
                # ALWAYS check index first - it's the most reliable indicator
                playhead_index = playhead_state.get("current_index", -1)
                index_differs = playhead_index >= 0 and playhead_index != expected_index
                
                if paths_differ or index_differs:
                    # Verify this is a valid skip (same playlist, different file)
                    # Use a more lenient mtime check (within 1 second) to handle filesystem timing differences
                    mtime_match = abs(playhead_mtime - playlist_mtime) < 1.0

                    # REMOVED time restrictions - always respect playhead if index differs
                    # The playhead index is the authoritative source, not timing
                    # Allow skip if index differs OR (path differs AND mtime matches)
                    # Index difference is always authoritative
                    playhead_updated_at = playhead_state.get("updated_at", 0.0)
                    current_time_check = time.time()
                    if index_differs or (paths_differ and mtime_match):
                        LOGGER.info(
                            "Skip detected: interrupting %s (index %d) to jump to %s (index %d) - mtime_match=%s, index_differs=%s, updated_at=%.2f, age=%.2fs",
                            src,
                            expected_index,
                            playhead_path,
                            playhead_index,
                            mtime_match,
                            index_differs,
                            playhead_updated_at,
                            current_time_check - playhead_updated_at if playhead_updated_at > 0 else 0,
                        )
                        # Terminate FFmpeg process
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            # Force kill if it doesn't terminate gracefully
                            process.kill()
                            process.wait()
                        return False  # Stream was interrupted
                    else:
                        LOGGER.debug(
                            "Skip check failed - mtime_match=%s, recent_update=%s, playhead_mtime=%s, playlist_mtime=%s, updated_at=%s, current_time=%s",
                            mtime_match,
                            recent_update,
                            playhead_mtime,
                            playlist_mtime,
                            playhead_updated_at,
                            current_time_check,
                        )

    # Process finished, check return code
    returncode = process.returncode
    if returncode != 0:
        # Check if it was terminated by us (skip) or failed for another reason
        stderr_output = (
            process.stderr.read().decode("utf-8", errors="ignore")
            if process.stderr
            else ""
        )
        if returncode == -15:  # SIGTERM (terminated by us)
            LOGGER.info("Stream interrupted: %s", src)
            return False
        else:
            LOGGER.error(
                "FFmpeg failed with return code %d for %s", returncode, src
            )
            if stderr_output:
                # Log more of the error to see what's wrong
                LOGGER.error("FFmpeg stderr (first 1000 chars): %s", stderr_output[:1000])
                # Also try to extract the actual error message
                error_lines = stderr_output.split('\n')
                for line in error_lines:
                    if any(keyword in line.lower() for keyword in ['error', 'failed', 'invalid', 'cannot', 'unable']):
                        LOGGER.error("FFmpeg error line: %s", line)
            return False

    return True


def record_playhead(src: str, index: int, playlist_mtime: float, force: bool = False) -> None:
    """Record playhead state, but don't overwrite if it was recently updated externally (skip command).
    
    Args:
        src: Path to the current file
        index: Index in the playlist
        playlist_mtime: Playlist modification time
        force: If True, always update even if recently updated externally (for post-stream updates)
    """
    # Check if playhead was recently updated externally (within last 2 seconds)
    # Only skip if it points to a different file (skip command), not if it's the same (normal playback)
    # Unless force=True, which allows updates after successful streaming
    if not force:
        existing_state = load_playhead_state(force_reload=True)
        if existing_state:
            existing_updated_at = existing_state.get("updated_at", 0.0)
            existing_path = existing_state.get("current_path")
            if existing_updated_at > 0 and (time.time() - existing_updated_at) < 2.0:
                # Check if the existing playhead points to a different file (skip command)
                if _normalize_path:
                    normalized_existing = (
                        _normalize_path(existing_path) if existing_path else None
                    )
                    normalized_src = _normalize_path(src)
                    paths_differ = (
                        normalized_existing != normalized_src
                        if normalized_existing
                        else True
                    )
                else:
                    paths_differ = existing_path != src if existing_path else True

                if paths_differ:
                    # Playhead was recently updated externally to a different file (skip command), don't overwrite
                    LOGGER.debug(
                        "Skipping playhead record - was recently updated externally to different file (age: %.2fs)",
                        time.time() - existing_updated_at,
                    )
                    return

    state = {
        "current_path": src,
        "current_index": index,
        "playlist_mtime": playlist_mtime,
        "playlist_path": PLAYLIST,
        "entry_type": entry_type(src),
    }
    save_playhead_state(state)

    # Sync playhead to host file if running in Docker (so API can read it)
    # The mount should handle this, but force sync to be sure
    try:
        import subprocess

        playhead_path = resolve_playhead_path()
        # Copy from container to host (reverse of what skip API does)
        result = subprocess.run(
            ["docker", "cp", "tvchannel:/app/hls/playhead.json", str(playhead_path)],
            capture_output=True,
            timeout=2,
        )
        if result.returncode != 0:
            # If that fails, try copying host to container (in case mount works the other way)
            pass
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        # Docker not available or copy failed - that's okay, the mount should handle it
        pass


def run_stream():
    last_played: Optional[str] = None
    next_index = 0
    # Cache valid files to avoid repeated file existence checks
    _valid_files_cache: Dict[str, bool] = {}
    _last_playlist_hash: Optional[int] = None

    while True:
        try:
            files, playlist_mtime = load_playlist()
        except FileNotFoundError as exc:
            LOGGER.warning("Playlist file not found: %s", exc)
            time.sleep(5)
            continue

        if not files:
            LOGGER.info("Playlist empty, waiting for media files...")
            time.sleep(10)
            continue

        # Check if playlist changed (simple hash check)
        playlist_hash = hash(tuple(files))
        if playlist_hash != _last_playlist_hash:
            # Playlist changed, rebuild cache
            _valid_files_cache.clear()
            _last_playlist_hash = playlist_hash

        # Process playlist entries - handle weather markers and validate files
        # Use cache to avoid repeated os.path.exists calls
        valid_files = []
        for file_path in files:
            # Weather bumpers and bumper blocks are markers, not files - keep them as-is
            if is_weather_bumper(file_path) or is_bumper_block(file_path):
                valid_files.append(file_path)
                continue
            
            # Check cache first for regular files
            if file_path in _valid_files_cache:
                if _valid_files_cache[file_path]:
                    valid_files.append(file_path)
                # If cached as invalid, skip it
            else:
                # Not in cache, check file existence
                is_valid = os.path.exists(file_path) and os.path.isfile(file_path)
                _valid_files_cache[file_path] = is_valid
                if is_valid:
                    valid_files.append(file_path)
                else:
                    LOGGER.warning("Skipping invalid playlist entry: %s", file_path)

        if not valid_files:
            LOGGER.info("No valid files in playlist, waiting...")
            time.sleep(10)
            continue

        files = valid_files

        # CRITICAL: Always start from playhead if available, not from last_played
        # This ensures we resume from where we actually are, not where we think we are
        playhead_state = load_playhead_state(force_reload=True)
        if playhead_state and playhead_state.get("current_index") is not None:
            playhead_index = playhead_state.get("current_index", -1)
            playhead_path = playhead_state.get("current_path")
            playhead_mtime = playhead_state.get("playlist_mtime", 0.0)
            
            # Check if playhead index is valid and playlist hasn't changed significantly
            if playhead_index >= 0 and playhead_index < len(files):
                # Verify the playhead path matches what's at that index (playlist might have changed)
                if _normalize_path:
                    normalized_playhead = _normalize_path(playhead_path) if playhead_path else None
                    normalized_at_index = _normalize_path(files[playhead_index]) if playhead_index < len(files) else None
                    path_matches = normalized_playhead == normalized_at_index
                else:
                    path_matches = playhead_path == files[playhead_index] if playhead_index < len(files) else False
                
                # Use playhead index if path matches OR if mtime is close (playlist might have shifted slightly)
                mtime_match = abs(playhead_mtime - playlist_mtime) < 5.0  # 5 second tolerance
                if path_matches or mtime_match:
                    next_index = playhead_index
                    LOGGER.info("Resuming from playhead: index %d (%s)", next_index, files[next_index] if next_index < len(files) else "invalid")
                else:
                    # Playhead doesn't match, search for it
                    try:
                        if _normalize_path and playhead_path:
                            normalized_playhead = _normalize_path(playhead_path)
                            for idx, file_path in enumerate(files):
                                if _normalize_path(file_path) == normalized_playhead:
                                    next_index = idx
                                    LOGGER.info("Found playhead path at index %d (was %d)", next_index, playhead_index)
                                    break
                            else:
                                next_index = 0
                        else:
                            next_index = files.index(playhead_path) if playhead_path in files else 0
                    except (ValueError, AttributeError):
                        next_index = 0
            else:
                # Playhead index is invalid, start from beginning or last_played
                if last_played:
                    try:
                        next_index = files.index(last_played) + 1
                    except ValueError:
                        next_index = 0
                else:
                    next_index = 0
        else:
            # No playhead state, use last_played or start from beginning
            if last_played:
                try:
                    next_index = files.index(last_played) + 1
                except ValueError:
                    next_index = 0
            else:
                next_index = 0

        while files:
            if next_index >= len(files):
                next_index = 0

            # CRITICAL: Always check playhead FIRST before determining what to stream
            # This ensures we always stream what the playhead says, not what we think should be next
            playhead_state = load_playhead_state(force_reload=True)
            playhead_updated_externally = False
            
            # If playhead exists and has a valid index, USE IT - this is the source of truth
            if playhead_state and playhead_state.get("current_index") is not None:
                playhead_index = playhead_state.get("current_index", -1)
                playhead_path = playhead_state.get("current_path")
                playhead_mtime = playhead_state.get("playlist_mtime", 0.0)
                
                # If playhead index is valid and different from what we were going to stream, use it
                if playhead_index >= 0 and playhead_index < len(files):
                    if playhead_index != next_index:
                        # Playhead points to a different file - use it (this handles skip commands)
                        next_index = playhead_index
                        playhead_updated_externally = True
                        LOGGER.info(
                            "Using playhead index %d instead of calculated index %d: %s",
                            playhead_index,
                            next_index if not playhead_updated_externally else "N/A",
                            files[playhead_index] if playhead_index < len(files) else "invalid"
                        )
            
            # Determine the normal next file to stream (may have been overridden by playhead above)
            normal_next_src = files[next_index]

            # Additional check: if playhead path differs from what we're about to stream, verify it
            if playhead_state and playhead_state.get("current_path"):
                playhead_path = playhead_state.get("current_path")
                playhead_index = playhead_state.get("current_index", -1)
                playhead_mtime = playhead_state.get("playlist_mtime", 0.0)

                # Normalize paths for comparison (handles container vs host path differences)
                if _normalize_path:
                    normalized_playhead = _normalize_path(playhead_path)
                    normalized_normal_next = _normalize_path(normal_next_src)
                    normalized_last_played = (
                        _normalize_path(last_played) if last_played else None
                    )
                    # Check if playhead path matches any file in the playlist (using normalized comparison)
                    playhead_matches = False
                    matching_index = -1
                    for idx, file_path in enumerate(files):
                        normalized_file = _normalize_path(file_path)
                        if normalized_file == normalized_playhead:
                            playhead_matches = True
                            matching_index = idx
                            break

                    # Only treat as external update if playhead points to a DIFFERENT file than normal flow
                    # AND it's not the file we just finished streaming (prevents loops)
                    playhead_differs_from_normal = (
                        normalized_playhead != normalized_normal_next
                    )
                    playhead_is_last_played = (
                        normalized_last_played
                        and normalized_playhead == normalized_last_played
                    )
                else:
                    # Fallback: direct comparison
                    playhead_matches = playhead_path in files
                    try:
                        matching_index = (
                            files.index(playhead_path) if playhead_matches else -1
                        )
                    except ValueError:
                        matching_index = -1
                    playhead_differs_from_normal = playhead_path != normal_next_src
                    playhead_is_last_played = (
                        last_played and playhead_path == last_played
                    )

                # If playhead was updated externally and points to a valid file DIFFERENT from normal flow, use it
                # This happens when the skip API updates the playhead
                # Use lenient mtime check or recent update check
                # BUT ignore if playhead points to the file we just finished (prevents infinite loops)
                mtime_match = abs(playhead_mtime - playlist_mtime) < 1.0
                playhead_updated_at = playhead_state.get("updated_at", 0.0)
                # REMOVED time window restriction - always respect playhead if index differs
                # The playhead is the source of truth, not timing
                playhead_index_matches = (
                    playhead_index >= 0
                    and playhead_index < len(files)
                    and playhead_index != next_index
                )
                
                # ALWAYS jump if playhead index differs - this is the most reliable indicator
                # Don't check timing - the playhead is always authoritative
                if (
                    playhead_matches
                    and playhead_differs_from_normal
                    and not playhead_is_last_played
                    and playhead_index_matches
                ):
                    # Prefer using playhead_index if it's valid, otherwise use matching_index
                    target_index = playhead_index if playhead_index_matches else matching_index
                    next_index = target_index
                    src = files[target_index]  # Use the actual file path from the playlist
                    playhead_updated_externally = True
                    LOGGER.info(
                        "Playhead updated externally: jumping to %s (index %d, playhead_index=%d)",
                        src,
                        next_index,
                        playhead_index,
                    )

            if not playhead_updated_externally:
                # Normal flow - use calculated next_index
                src = normal_next_src

            # Handle bumper block markers - generate or use pre-generated block
            if is_bumper_block(src):
                # Check playhead first - if skip was triggered, use playhead index instead
                playhead_state = load_playhead_state(force_reload=True)
                if playhead_state and playhead_state.get("current_index") is not None:
                    playhead_index = playhead_state.get("current_index", -1)
                    if playhead_index >= 0 and playhead_index < len(files) and playhead_index != next_index:
                        # Skip was triggered, jump to playhead index
                        next_index = playhead_index
                        LOGGER.info("Skip detected before bumper block, jumping to index %d", next_index)
                        continue  # Re-check what to stream at new index
                
                block = _resolve_bumper_block(next_index, files)
                if block and block.bumpers:
                    # Stream all bumpers in the block sequentially
                    block_interrupted = False
                    for bumper_path in block.bumpers:
                        if os.path.exists(bumper_path):
                            LOGGER.info("Streaming bumper from block: %s", bumper_path)
                            bumper_streamed = stream_file(bumper_path, next_index, playlist_mtime)
                            if not bumper_streamed:
                                # Stream was interrupted (skip command), check playhead for new target
                                playhead_state = load_playhead_state(force_reload=True)
                                if playhead_state and playhead_state.get("current_index") is not None:
                                    playhead_index = playhead_state.get("current_index", -1)
                                    if playhead_index >= 0 and playhead_index < len(files):
                                        next_index = playhead_index
                                        LOGGER.info("Skip detected during bumper block, jumping to index %d", next_index)
                                        block_interrupted = True
                                        break  # Exit bumper loop, will continue with new target
                    
                    if block_interrupted:
                        continue  # Re-check what to stream at new index
                    
                    # Pre-generate next bumper block while we're streaming
                    _queue_next_bumper_block(next_index, files)
                    
                    # Advance to next entry after block
                    next_index += 1
                    if next_index >= len(files):
                        next_index = 0
                    continue
                else:
                    LOGGER.warning("Failed to resolve bumper block, skipping")
                    next_index += 1
                    if next_index >= len(files):
                        next_index = 0
                    continue
            
            # Handle weather bumper markers - render on-the-fly (legacy support)
            if is_weather_bumper(src):
                weather_path = _render_weather_bumper_jit()
                if weather_path:
                    src = weather_path
                    LOGGER.info("Rendered weather bumper on-the-fly: %s", weather_path)
                else:
                    LOGGER.warning("Failed to render weather bumper, skipping")
                    # Advance to next entry
                    next_index += 1
                    if next_index >= len(files):
                        next_index = 0
                    continue

            # Record playhead when we START streaming a file (not just when it finishes)
            # This ensures the playhead always reflects what's currently playing
            # Only record if it wasn't updated externally (to avoid overwriting skip commands)
            # Skip recording for weather bumpers and bumper blocks (they're temporary/markers)
            if not playhead_updated_externally and not is_weather_bumper(src) and not is_bumper_block(src):
                record_playhead(src, next_index, playlist_mtime)
                LOGGER.info("Recorded playhead at stream start: %s (index %d)", src, next_index)
                
                # Pre-generate next bumper block while episode is playing
                _queue_next_bumper_block(next_index, files)

            # Stream the file and only mark as watched if streaming succeeded
            # Pass index and mtime so stream_file can detect if skip was triggered
            streaming_succeeded = stream_file(src, next_index, playlist_mtime)

            # If stream was interrupted (skip), check playhead again to get the new target
            stream_was_skipped = False
            if not streaming_succeeded:
                playhead_state = load_playhead_state(force_reload=True)
                if playhead_state and playhead_state.get("current_path"):
                    playhead_path = playhead_state.get("current_path")
                    playhead_mtime = playhead_state.get("playlist_mtime", 0.0)

                    # Normalize paths for comparison
                    if _normalize_path:
                        normalized_playhead = _normalize_path(playhead_path)
                        normalized_src = _normalize_path(src)
                        paths_differ = normalized_playhead != normalized_src
                    else:
                        paths_differ = playhead_path != src

                    # Check if playhead points to a different file (skip was triggered)
                    if paths_differ:
                        # Find the matching file in the playlist using normalized comparison
                        matching_index = -1
                        for idx, file_path in enumerate(files):
                            if _normalize_path:
                                normalized_file = _normalize_path(file_path)
                                if normalized_file == normalized_playhead:
                                    matching_index = idx
                                    break
                            else:
                                if file_path == playhead_path:
                                    matching_index = idx
                                    break

                        # Use lenient mtime check or recent update check
                        # Increase window to 30 seconds to account for time between detection and jump
                        mtime_match = abs(playhead_mtime - playlist_mtime) < 1.0
                        playhead_updated_at = playhead_state.get("updated_at", 0.0)
                        current_time_check = time.time()
                        recent_update = (
                            playhead_updated_at > 0
                            and (current_time_check - playhead_updated_at) < 30.0
                        )

                        if matching_index >= 0 and (mtime_match or recent_update):
                            next_index = matching_index
                            src = files[
                                matching_index
                            ]  # Use the actual file path from the playlist
                            stream_was_skipped = True
                            LOGGER.info(
                                "Jumping to skipped episode: %s (index %d)",
                                src,
                                next_index,
                            )
                            # Continue to next iteration to stream the skipped-to file
                            continue
                        else:
                            LOGGER.debug(
                                "Skip target not found or invalid - matching_index=%s, mtime_match=%s, recent_update=%s",
                                matching_index,
                                mtime_match,
                                recent_update,
                            )

            last_played = src

            # Mark episode as watched only if streaming completed successfully (not interrupted)
            if streaming_succeeded and is_episode_entry(src) and not stream_was_skipped:
                mark_episode_watched(src)
            elif not streaming_succeeded and not stream_was_skipped:
                LOGGER.warning(
                    "Skipping watch progress update for failed stream: %s", src
                )

            try:
                files, playlist_mtime = load_playlist()
            except FileNotFoundError as exc:
                LOGGER.warning("Playlist file not found after update: %s", exc)
                time.sleep(5)
                break

            if not files:
                LOGGER.info("Playlist empty after update, waiting...")
                time.sleep(10)
                break

            # Advance to next index after successful streaming
            # CRITICAL: Use the current next_index and increment it, don't search for last_played
            # This prevents loops when the playlist changes or files are missing
            if streaming_succeeded and not stream_was_skipped:
                # Simply increment next_index - it already points to the file we just streamed
                # So the next file is at next_index + 1
                next_index += 1
                
                # Wrap around if we've reached the end
                if next_index >= len(files):
                    next_index = 0
                    LOGGER.info("Reached end of playlist, wrapping to beginning")
                
                # Update playhead to point to the next file after successful streaming
                # This ensures the playhead reflects the actual playback position
                # CRITICAL: Always update playhead after successful streaming to prevent loops
                # Use force=True to ensure the playhead is updated even if it was recently updated externally
                if next_index < len(files):
                    next_src = files[next_index]
                    # Skip recording for weather bumpers and bumper blocks (they're temporary/markers)
                    if not is_weather_bumper(next_src) and not is_bumper_block(next_src):
                        record_playhead(next_src, next_index, playlist_mtime, force=True)
                        LOGGER.info("Updated playhead to next file after successful stream: %s (index %d)", next_src, next_index)
                else:
                    LOGGER.warning("next_index %d is out of bounds for playlist with %d files", next_index, len(files))
            elif not streaming_succeeded and not stream_was_skipped:
                # If streaming failed, skip to next file to prevent infinite loops
                # We'll try again on the next playlist cycle if the file becomes available
                LOGGER.warning("Streaming failed for %s, skipping to next file", src)
                next_index += 1
                if next_index >= len(files):
                    next_index = 0
                # Update playhead to next file to prevent retrying the failed file
                if next_index < len(files):
                    next_src = files[next_index]
                    # Skip recording for weather bumpers and bumper blocks (they're temporary/markers)
                    if not is_weather_bumper(next_src) and not is_bumper_block(next_src):
                        record_playhead(next_src, next_index, playlist_mtime, force=True)
                        LOGGER.info("Updated playhead to next file after stream failure: %s (index %d)", next_src, next_index)


if __name__ == "__main__":
    # Configure logging to ensure messages are visible
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Start bumper block pre-generation thread
    try:
        from server.bumper_block import get_generator
        generator = get_generator()
        generator.start_pregen_thread()
        LOGGER.info("Started bumper block pre-generation")
    except Exception as e:
        LOGGER.warning(f"Failed to start bumper block pre-generation: {e}")
    
    run_stream()
