#!/usr/bin/env python3
"""
Clean streaming server rewrite.
Simple state machine: Episode -> Bumper Block -> Episode
Pre-generates bumper blocks before episodes finish.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import logging
import os
import queue
import random
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)

try:
    from playlist_service import (
        entry_type,
        is_episode_entry,
        is_weather_bumper as playlist_is_weather_bumper,
        load_playhead_state,
        load_playlist_entries,
        mark_episode_watched,
        resolve_playhead_path,
        resolve_playlist_path,
        save_playhead_state,
    )
    try:
        from playlist_service import _normalize_path
    except ImportError:
        _normalize_path = None
except ImportError:
    repo_root = Path(__file__).resolve().parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from server.playlist_service import (
        entry_type,
        is_episode_entry,
        is_weather_bumper as playlist_is_weather_bumper,
        load_playhead_state,
        load_playlist_entries,
        mark_episode_watched,
        resolve_playhead_path,
        resolve_playlist_path,
        save_playhead_state,
    )
    try:
        from server.playlist_service import _normalize_path
    except ImportError:
        _normalize_path = None

# Constants
BUMPER_BLOCK_MARKER = "BUMPER_BLOCK"
# Support both Docker (/app/hls) and baremetal (server/hls) paths
if Path("/app/hls").exists():
    HLS_DIR = Path("/app/hls")
else:
    # Running baremetal - use relative path
    HLS_DIR = Path(__file__).parent.parent / "server" / "hls"
OUTPUT = HLS_DIR / "stream.m3u8"
# Support both Docker and baremetal paths for bug image
if Path("/app/assets/branding/hbn_logo_bug.png").exists():
    BUG_IMAGE_PATH = Path("/app/assets/branding/hbn_logo_bug.png")
else:
    # Running baremetal - use relative path
    BUG_IMAGE_PATH = Path(__file__).parent.parent / "assets" / "branding" / "hbn_logo_bug.png"
STREAMER_LOCK_FILE = HLS_DIR / "streamer.lock"
STREAMER_PID_FILE = HLS_DIR / "streamer.pid"

_lock_file_handle = None


def is_bumper_block(entry: str) -> bool:
    """Check if entry is a bumper block marker.
    
    Uses playlist_service for consistency, but checks for BUMPER_BLOCK marker specifically.
    """
    return entry.strip().upper() == BUMPER_BLOCK_MARKER


def is_weather_bumper(entry: str) -> bool:
    """Check if entry is a weather bumper marker.
    
    Uses playlist_service function for consistency.
    """
    return playlist_is_weather_bumper(entry)


# Use unified playlist loading from playlist_service
load_playlist = load_playlist_entries


def reset_hls_output(reason: str = "") -> None:
    """Reset HLS output for clean transition.
    
    We write a fresh playlist header with a discontinuity marker.
    FFmpeg will append new segments with discont_start flag, and old segments
    will be cleaned up by FFmpeg's delete_segments flag once they're out of the window.
    
    IMPORTANT: We do NOT delete segments here - deleting segments while FFmpeg
    is still writing or the client is still reading causes buffer holes.
    FFmpeg's delete_segments flag will handle cleanup automatically.
    """
    try:
        # Write fresh playlist header with discontinuity marker
        # FFmpeg will append new segments, and old segments will be cleaned up
        # by FFmpeg's delete_segments flag once they're out of the window
        with open(OUTPUT, "w", encoding="utf-8") as playlist:
            playlist.write("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:6\n#EXT-X-INDEPENDENT-SEGMENTS\n#EXT-X-DISCONTINUITY\n")
        if reason:
            LOGGER.info("Reset HLS playlist (%s)", reason)
    except Exception as exc:
        LOGGER.warning("Failed to reset HLS output: %s", exc)


def stream_file(src: str, index: int, playlist_mtime: float, disable_skip_detection: bool = False) -> bool:
    """Stream a single file (episode or bumper) to HLS.
    
    Args:
        src: Path to file to stream
        index: Index in playlist (for skip detection)
        playlist_mtime: Playlist modification time
        disable_skip_detection: If True, skip detection is disabled (for bumper blocks)
    """
    if not os.path.exists(src):
        LOGGER.error("File does not exist: %s", src)
        return False
    
    LOGGER.info("Streaming: %s (index %d)", Path(src).name, index)
    
    # Build FFmpeg command
    cmd = [
        "ffmpeg",
        "-re",  # Real-time streaming
        "-i", src,
    ]
    
    # Add logo overlay if bug image exists
    if BUG_IMAGE_PATH.exists():
        cmd.extend([
            "-loop", "1",
            "-i", str(BUG_IMAGE_PATH),
            "-filter_complex",
            "[1]format=rgba,colorchannelmixer=aa=0.8[logo_base];"
            "[logo_base]scale=-1:92[logo_scaled];"
            "[0][logo_scaled]overlay=x=main_w-overlay_w-40:y=40:shortest=1[vout]",
            "-map", "[vout]",
        ])
    else:
        cmd.extend(["-map", "0:v"])
    
    cmd.extend([
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-maxrate", "3000k",
        "-bufsize", "9000k",
        "-g", "60",
        "-sc_threshold", "0",
        "-force_key_frames", "expr:gte(t,n_forced*6)",
        "-keyint_min", "60",
        "-c:a", "aac",
        "-ac", "2",
        "-ar", "48000",
        "-b:a", "128k",
        "-f", "hls",
        "-hls_time", "6",
        "-hls_list_size", "50",
        "-hls_flags", "delete_segments+append_list+omit_endlist+discont_start+program_date_time+independent_segments",
        "-hls_segment_type", "mpegts",
        "-hls_segment_filename", str(HLS_DIR / "stream%04d.ts"),
        str(OUTPUT),
    ])
    
    # Clean up any orphaned FFmpeg processes
    cleanup_orphaned_ffmpeg_processes()
    time.sleep(0.5)
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        # Wait for FFmpeg to start and produce first segment before continuing
        # This ensures segments are available when client requests them
        time.sleep(1.0)
        if process.poll() is not None:
            LOGGER.error("FFmpeg exited immediately with return code %d", process.returncode)
            return False
        
        # Verify FFmpeg is producing segments
        max_wait = 5.0
        wait_start = time.time()
        segment_produced = False
        while (time.time() - wait_start) < max_wait:
            segment_files = list(HLS_DIR.glob("stream*.ts"))
            if segment_files:
                # Check if a new segment was created recently
                latest = max(segment_files, key=lambda p: p.stat().st_mtime)
                if (time.time() - latest.stat().st_mtime) < 2.0:
                    segment_produced = True
                    break
            time.sleep(0.2)
        
        if not segment_produced:
            LOGGER.warning("FFmpeg started but no segments produced after %ds", max_wait)
            # Don't fail here - FFmpeg might just be slow
        
        # Wait for process to complete
        # Add timeout to prevent infinite hangs
        start_time = time.time()
        max_duration = 3600  # 1 hour max per file (should be plenty for any video)
        last_segment_time = time.time()
        
        while process.poll() is None:
            # Check for timeout
            elapsed = time.time() - start_time
            if elapsed > max_duration:
                LOGGER.error("Stream timeout after %ds for %s, killing process", elapsed, Path(src).name)
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                return False
            
            # Check for skip command (disabled for bumper blocks to prevent false interrupts)
            if not disable_skip_detection:
                playhead_state = load_playhead_state(force_reload=True)
                if playhead_state:
                    playhead_index = playhead_state.get("current_index", -1)
                    playhead_path = playhead_state.get("current_path", "")
                    # Only skip if playhead has moved to a significantly different index
                    if playhead_index >= 0 and playhead_index != index:
                        # Only skip if the difference is significant (more than 1)
                        # This allows for minor index differences during normal playback
                        if abs(playhead_index - index) > 1:
                            LOGGER.info("Skip detected (playhead index %d != stream index %d), interrupting stream", playhead_index, index)
                            process.terminate()
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait()
                            return False
            
            # Check if FFmpeg is still producing segments (for completion detection)
            segment_files = list(HLS_DIR.glob("stream*.ts"))
            if segment_files:
                latest = max(segment_files, key=lambda p: p.stat().st_mtime)
                if latest.stat().st_mtime > last_segment_time:
                    last_segment_time = latest.stat().st_mtime
            
            time.sleep(0.5)
        
        returncode = process.returncode
        if returncode == 0:
            LOGGER.info("Stream completed successfully: %s", Path(src).name)
            return True
        else:
            LOGGER.error("FFmpeg failed with return code %d for %s", returncode, src)
            return False
    except Exception as e:
        LOGGER.error("Failed to stream %s: %s", src, e)
        return False


def _render_weather_bumper_jit() -> Optional[str]:
    """Render a weather bumper just-in-time for playback.
    
    Has timeout protection to prevent hangs.
    """
    try:
        from scripts.bumpers.render_weather_bumper import render_weather_bumper
    except ImportError:
        repo_root = Path(__file__).resolve().parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from scripts.bumpers.render_weather_bumper import render_weather_bumper
    
    temp_dir = HLS_DIR / "weather_temp"
    temp_dir.mkdir(exist_ok=True)
    out_path = temp_dir / f"weather_{int(time.time())}.mp4"
    
    # Add timeout protection for JIT rendering
    result_queue = queue.Queue(maxsize=1)
    
    def render_bumper():
        try:
            success = render_weather_bumper(str(out_path))
            result_queue.put(('success', success), timeout=1.0)
        except Exception as e:
            try:
                result_queue.put(('error', e), timeout=1.0)
            except queue.Full:
                pass
    
    # Start rendering in a thread
    thread = threading.Thread(target=render_bumper, daemon=True)
    thread.start()
    
    # Wait for result with timeout (20 seconds for weather rendering)
    try:
        result_type, result_value = result_queue.get(timeout=20.0)
        if result_type == 'success':
            success = result_value
        else:
            raise result_value
    except queue.Empty:
        LOGGER.warning("Weather bumper JIT rendering timed out after 20s")
        return None
    except Exception as e:
        LOGGER.warning("Weather bumper JIT rendering failed: %s", e)
        return None
    
    if success and out_path.exists():
        LOGGER.info("Successfully rendered weather bumper JIT: %s", Path(out_path).name)
        return str(out_path)
    
    LOGGER.warning("Failed to render weather bumper JIT")
    return None


def _render_up_next_bumper_jit(
    show_title: str, episode_metadata: Optional[Dict[str, Optional[int]]] = None
) -> Optional[str]:
    """Render a specific-episode up-next bumper just-in-time for playback.
    
    Only generates specific-episode bumpers (with episode metadata).
    Generic bumpers should already exist as files.
    
    Has timeout protection to prevent hangs.
    """
    if not episode_metadata:
        # No episode metadata means this should be a generic bumper (already exists)
        return None
    
    try:
        from scripts.bumpers.render_up_next_fast import render_up_next_bumper_fast, get_up_next_background_path
        from server.generate_playlist import format_episode_label
    except ImportError:
        repo_root = Path(__file__).resolve().parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from scripts.bumpers.render_up_next_fast import render_up_next_bumper_fast, get_up_next_background_path
        from server.generate_playlist import format_episode_label
    
    # Check if backgrounds are available
    bg_path = get_up_next_background_path()
    if not bg_path:
        LOGGER.warning("No up-next backgrounds available for JIT rendering")
        return None
    
    # Create temporary directory for JIT bumpers
    temp_dir = HLS_DIR / "up_next_temp"
    temp_dir.mkdir(exist_ok=True)
    
    # Generate unique filename
    episode_code = format_episode_label(episode_metadata) or "unknown"
    safe_episode = "".join(c if c.isalnum() or c in "._-" else "_" for c in episode_code)
    out_path = temp_dir / f"upnext_{int(time.time())}_{safe_episode}.mp4"
    
    # Use a random background for variety
    background_id = random.randint(0, 4)
    
    LOGGER.info("Rendering specific-episode up-next bumper JIT: %s - %s", show_title, episode_code)
    
    # Add timeout protection for JIT rendering
    result_queue = queue.Queue(maxsize=1)
    
    def render_bumper():
        try:
            success = render_up_next_bumper_fast(
                show_title=show_title,
                output_path=str(out_path),
                episode_label=format_episode_label(episode_metadata),
                background_id=background_id,
            )
            result_queue.put(('success', success), timeout=1.0)
        except Exception as e:
            try:
                result_queue.put(('error', e), timeout=1.0)
            except queue.Full:
                pass
    
    # Start rendering in a thread
    thread = threading.Thread(target=render_bumper, daemon=True)
    thread.start()
    
    # Wait for result with timeout (15 seconds for JIT rendering)
    try:
        result_type, result_value = result_queue.get(timeout=15.0)
        if result_type == 'success':
            success = result_value
        else:
            raise result_value
    except queue.Empty:
        LOGGER.warning("Up-next bumper JIT rendering timed out after 15s for %s - %s", show_title, episode_code)
        return None
    except Exception as e:
        LOGGER.warning("Up-next bumper JIT rendering failed: %s", e)
        return None
    
    if success and out_path.exists():
        LOGGER.info("Successfully rendered up-next bumper JIT: %s", Path(out_path).name)
        return str(out_path)
    
    LOGGER.warning("Failed to render up-next bumper JIT for %s - %s", show_title, episode_code)
    return None


def cleanup_bumpers(bumper_paths: list[str]) -> None:
    """
    Clean up (delete) bumper files after they've been used.
    Deletes:
    - JIT-generated up-next bumpers (from up_next_temp directory)
    - JIT-generated weather bumpers (from weather_temp directory)
    Does NOT delete:
    - Generic up-next bumpers (show.mp4) - these are reused
    - Sassy cards
    - Network bumpers
    """
    for bumper_path in bumper_paths:
        if not bumper_path:
            continue
        
        try:
            bumper_file = Path(bumper_path)
            if not bumper_file.exists() or not bumper_file.is_file():
                continue
            
            # Delete JIT-generated bumpers (temporary directories)
            if "/up_next_temp/" in bumper_path or "/weather_temp/" in bumper_path:
                bumper_file.unlink()
                LOGGER.info("Cleaned up JIT bumper: %s", bumper_file.name)
        except Exception as e:
            LOGGER.warning("Failed to cleanup bumper %s: %s", bumper_path, e)


def _should_include_weather(episode_path: str) -> bool:
    """Check if weather bumper should be included based on probability.
    
    Uses deterministic seed based on episode path for consistency.
    """
    try:
        from server.generate_playlist import load_weather_config
        weather_cfg = load_weather_config()
        if not weather_cfg.get("enabled", False):
            return False
        
        weather_prob = weather_cfg.get("probability_between_episodes", 0.0)
        if weather_prob <= 0:
            return False
        
        # Use deterministic seed based on episode path for consistency
        seed = int(hashlib.md5(episode_path.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        return rng.random() <= weather_prob
    except Exception as e:
        LOGGER.debug("Failed to check weather config: %s", e)
        return False


def _get_up_next_bumper(episode_path: str) -> Optional[str]:
    """Get up-next bumper for an episode (generic or JIT-rendered specific)."""
    try:
        from server.generate_playlist import (
            find_existing_bumper,
            extract_episode_metadata,
            infer_show_title_from_path,
            ensure_bumper,
        )
        from pathlib import Path
        
        show_label = infer_show_title_from_path(episode_path)
        metadata = extract_episode_metadata(episode_path)
        
        LOGGER.info("_get_up_next_bumper: Episode=%s, Show=%s, Metadata=%s", 
                   Path(episode_path).name, show_label, metadata)
        
        # Try to get generic bumper first (saved as file)
        up_next_bumper = find_existing_bumper(show_label, metadata)
        
        if up_next_bumper:
            LOGGER.info("_get_up_next_bumper: Found existing bumper: %s", Path(up_next_bumper).name)
        else:
            LOGGER.info("_get_up_next_bumper: No existing bumper found for %s, generating...", show_label)
            # Try to generate generic bumper if it doesn't exist
            try:
                up_next_bumper = ensure_bumper(show_label, None)  # Only generate generic
                if up_next_bumper:
                    LOGGER.info("_get_up_next_bumper: Generated bumper: %s", Path(up_next_bumper).name)
            except Exception as e:
                LOGGER.warning("Could not get generic up-next bumper for %s: %s", show_label, e)
                return None
        
        # If we have episode metadata, render specific-episode bumper JIT
        if metadata:
            LOGGER.info("_get_up_next_bumper: Rendering JIT bumper for %s with metadata %s", show_label, metadata)
            jit_bumper = _render_up_next_bumper_jit(show_label, metadata)
            if jit_bumper:
                LOGGER.info("_get_up_next_bumper: JIT bumper rendered: %s", Path(jit_bumper).name)
                up_next_bumper = jit_bumper  # Use JIT bumper instead of generic
            else:
                LOGGER.warning("_get_up_next_bumper: JIT bumper rendering failed, using generic: %s", 
                             Path(up_next_bumper).name if up_next_bumper else "None")
        
        LOGGER.info("_get_up_next_bumper: Final bumper for %s: %s", show_label, 
                   Path(up_next_bumper).name if up_next_bumper else "None")
        return up_next_bumper
    except Exception as e:
        LOGGER.error("Failed to get up-next bumper: %s", e, exc_info=True)
        return None


def _add_weather_to_block(block: Any) -> None:
    """Add weather bumper to a block if it's missing, inserting in correct order."""
    if not block or not block.bumpers:
        return
    
    # Check if weather already exists
    has_weather = any("/weather_temp/" in b or "/bumpers/weather/" in b for b in block.bumpers)
    if has_weather:
        return
    
    # Render weather bumper JIT
    try:
        weather_bumper = _render_weather_bumper_jit()
        if not weather_bumper or not os.path.exists(weather_bumper):
            LOGGER.warning("Failed to render weather bumper for block")
            return
        
        # Insert weather bumper in correct order: sassy, weather, up-next, network
        insert_pos = 0
        for i, bumper in enumerate(block.bumpers):
            if "/bumpers/sassy/" in bumper:
                insert_pos = i + 1
                break
            elif "/bumpers/up_next/" in bumper or "/up_next_temp/" in bumper:
                insert_pos = i
                break
        
        block.bumpers.insert(insert_pos, weather_bumper)
        LOGGER.info("Added weather bumper to block at position %d (total bumpers: %d)", insert_pos, len(block.bumpers))
    except Exception as e:
        LOGGER.warning("Failed to add weather bumper to block: %s", e)


def resolve_bumper_block(next_episode_index: int, files: List[str]) -> Optional[Any]:
    """Resolve a bumper block for the next episode.
    
    Unified logic for all bumper block resolution:
    1. Check weather probability (deterministic)
    2. Get up-next bumper (generic + JIT if needed)
    3. Try to get pre-generated block
    4. Add weather if missing
    5. Generate on-the-fly if no block available
    """
    try:
        repo_root = Path(__file__).resolve().parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from server.bumper_block import get_generator
        
        if next_episode_index >= len(files):
            return None
        
        next_episode = files[next_episode_index]
        if not os.path.exists(next_episode):
            return None
        
        # Check weather probability
        should_include_weather = _should_include_weather(next_episode)
        weather_bumper_marker = "WEATHER_BUMPER" if should_include_weather else None
        if should_include_weather:
            LOGGER.info("Weather bumper should be included for episode: %s", Path(next_episode).name)
        
        # Get up-next bumper
        up_next_bumper = _get_up_next_bumper(next_episode)
        if not up_next_bumper:
            LOGGER.warning("Could not get up-next bumper for %s", Path(next_episode).name)
            return None
        
        generator = get_generator()
        
        # Try to get pre-generated block (by spec hash first, then by episode path, then any)
        block = None
        
        # Try by spec hash
        if up_next_bumper:
            block = generator.get_pregenerated_block(
                up_next_bumper=up_next_bumper,
                sassy_card=None,
                network_bumper=None,
                weather_bumper=weather_bumper_marker,
            )
        
        # Try by episode path
        if not block:
            block = generator.get_next_pregenerated_block(episode_path=next_episode)
        
        # Try any available
        if not block:
            block = generator.get_next_pregenerated_block(episode_path=None)
        
        # If we got a block, ensure it has the correct up-next bumper for this episode
        if block:
            # Replace up-next bumper with the correct one for this episode
            # Pre-generated blocks may have been created for a different episode
            if block.bumpers and up_next_bumper:
                up_next_replaced = False
                # Find and replace the up-next bumper in the block
                for i, bumper_path in enumerate(block.bumpers):
                    # Check if this is an up-next bumper (generic or JIT)
                    if "/bumpers/up_next/" in bumper_path or "/up_next_temp/" in bumper_path:
                        # Replace with correct up-next bumper for this episode
                        old_bumper_name = Path(bumper_path).name
                        new_bumper_name = Path(up_next_bumper).name
                        if bumper_path != up_next_bumper:
                            LOGGER.info("Replacing up-next bumper in pre-generated block: %s -> %s", 
                                      old_bumper_name, new_bumper_name)
                            block.bumpers[i] = up_next_bumper
                            up_next_replaced = True
                        else:
                            LOGGER.debug("Up-next bumper already correct: %s", new_bumper_name)
                            up_next_replaced = True
                        break
                
                if not up_next_replaced:
                    LOGGER.warning("Could not find up-next bumper in pre-generated block to replace. Block bumpers: %s", 
                                 [Path(b).name for b in block.bumpers])
            
            # Ensure weather is included if needed
            if should_include_weather:
                _add_weather_to_block(block)
            
            LOGGER.info("Using pre-generated bumper block for episode %s", Path(next_episode).name)
            return block
        
        # Last resort: generate on-the-fly
        LOGGER.warning("No pre-generated block available, generating on-the-fly for %s", Path(next_episode).name)
        
        weather_bumper = None
        if should_include_weather:
            try:
                weather_bumper = _render_weather_bumper_jit()
            except Exception as e:
                LOGGER.warning("Failed to render weather bumper: %s", e)
        
        block = generator.generate_block(
            up_next_bumper=up_next_bumper,
            sassy_card=None,  # Auto-draw
            network_bumper=None,  # Auto-draw
            weather_bumper=weather_bumper,
            skip_music=False,  # Include music
        )
        
        return block
    except Exception as e:
        LOGGER.error("Failed to resolve bumper block: %s", e, exc_info=True)
        return None


def pregenerate_next_bumper_block(current_index: int, files: List[str]) -> None:
    """Pre-generate bumper block for the episode that comes after the next BUMPER_BLOCK marker.
    
    When an episode is playing, we pre-generate the bumper block that will play BEFORE
    the next episode. This ensures the bumper block is ready when the current episode ends.
    """
    try:
        from server.bumper_block import get_generator
        
        # Find the next BUMPER_BLOCK marker after the current episode
        bumper_block_idx = current_index + 1
        while bumper_block_idx < len(files) and not is_bumper_block(files[bumper_block_idx]):
            bumper_block_idx += 1
        
        if bumper_block_idx >= len(files):
            # No bumper block found, nothing to pre-generate
            return
        
        # Find the episode that comes right after this BUMPER_BLOCK marker
        next_episode_idx = bumper_block_idx + 1
        while next_episode_idx < len(files) and not is_episode_entry(files[next_episode_idx]):
            next_episode_idx += 1
        
        if next_episode_idx >= len(files):
            # No episode found after bumper block
            return
        
        next_episode = files[next_episode_idx]
        if not os.path.exists(next_episode):
            return
        
        # Get up-next bumper using unified logic
        up_next_bumper = _get_up_next_bumper(next_episode)
        if not up_next_bumper:
            return
        
        # Check weather probability using unified logic
        should_include_weather = _should_include_weather(next_episode)
        weather_bumper_marker = "WEATHER_BUMPER" if should_include_weather else None
        
        # Queue for pre-generation
        generator = get_generator()
        if not generator._pregen_thread or not generator._pregen_thread.is_alive():
            LOGGER.info("Starting bumper block pre-generation thread")
            generator.start_pregen_thread()
        
        generator.queue_pregen({
            "up_next_bumper": up_next_bumper,
            "sassy_card": None,
            "network_bumper": None,
            "weather_bumper": weather_bumper_marker,
            "episode_path": next_episode,
        })
        LOGGER.info("Queued bumper block pre-generation for episode: %s (will play after BUMPER_BLOCK at index %d)", 
                   Path(next_episode).name, bumper_block_idx)
    except Exception as e:
        LOGGER.warning("Failed to pre-generate bumper block: %s", e, exc_info=True)


def update_playhead(path: str, index: int, playlist_mtime: float) -> None:
    """Update playhead state."""
    try:
        state = {
            "current_path": path,
            "current_index": index,
            "playlist_mtime": playlist_mtime,
            "playlist_path": str(resolve_playlist_path()),
            "entry_type": entry_type(path),
            "updated_at": time.time(),
        }
        save_playhead_state(state)
    except Exception as e:
        LOGGER.warning("Failed to update playhead: %s", e)


def cleanup_orphaned_ffmpeg_processes() -> None:
    """Kill any FFmpeg processes streaming to our HLS output."""
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.split("\n"):
            if "ffmpeg" in line.lower() and "stream.m3u8" in line:
                parts = line.split()
                if len(parts) > 1:
                    try:
                        pid = int(parts[1])
                        os.kill(pid, signal.SIGKILL)
                        LOGGER.debug("Killed orphaned FFmpeg process %d", pid)
                    except (ValueError, ProcessLookupError):
                        pass
    except Exception:
        pass
    

def acquire_streamer_lock() -> bool:
    """Acquire exclusive lock for streamer."""
    global _lock_file_handle
    try:
        HLS_DIR.mkdir(parents=True, exist_ok=True)
        lock_file = open(STREAMER_LOCK_FILE, "w")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file_handle = lock_file
        return True
    except BlockingIOError:
        lock_file.close()
        try:
            if STREAMER_LOCK_FILE.exists():
                with STREAMER_LOCK_FILE.open("r") as f:
                    other_pid = int(f.read().strip())
                try:
                    os.kill(other_pid, 0)
                    LOGGER.warning("Another streamer is running (PID %d)", other_pid)
                    return False
                except ProcessLookupError:
                    STREAMER_LOCK_FILE.unlink(missing_ok=True)
                    return acquire_streamer_lock()
        except Exception:
            STREAMER_LOCK_FILE.unlink(missing_ok=True)
            return acquire_streamer_lock()
    except Exception as e:
        LOGGER.error("Failed to acquire lock: %s", e)
        return False


def cleanup_on_exit() -> None:
    """Clean up on exit."""
    global _lock_file_handle
    try:
        if _lock_file_handle:
            _lock_file_handle.close()
            _lock_file_handle = None
        STREAMER_LOCK_FILE.unlink(missing_ok=True)
        STREAMER_PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def run_stream() -> None:
    """Main streaming loop - clean and simple."""
    current_index = 0

    while True:
        try:
            # Load playlist
            LOGGER.info("Loading playlist...")
            files, playlist_mtime = load_playlist()
            LOGGER.info("Loaded %d entries from playlist", len(files))
            
            # Filter to valid files only
            valid_files = []
            for f in files:
                if is_bumper_block(f) or is_weather_bumper(f):
                    valid_files.append(f)
                elif os.path.exists(f):
                    valid_files.append(f)

            if not valid_files:
                LOGGER.warning("No valid files in playlist, waiting for playlist generation...")
                # Reset HLS output to prevent stale segments
                reset_hls_output(reason="empty_playlist")
                time.sleep(10)
                continue

            files = valid_files
            LOGGER.info("Filtered to %d valid entries", len(files))

            # Get current position from playhead
            # First, check what FFmpeg is actually streaming (if anything)
            # This is the source of truth for what's currently playing
            ffmpeg_streaming_file = None
            try:
                result = subprocess.run(
                    ["ps", "aux"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                for line in result.stdout.split("\n"):
                    if "ffmpeg" in line.lower() and "stream.m3u8" in line and "-i" in line:
                        # Extract the input file from FFmpeg command
                        parts = line.split()
                        try:
                            i_idx = parts.index("-i")
                            if i_idx + 1 < len(parts):
                                potential_file = parts[i_idx + 1]
                                # Check if it's a valid file path (not a filter or option)
                                if os.path.exists(potential_file) and os.path.isfile(potential_file):
                                    ffmpeg_streaming_file = potential_file
                                    LOGGER.info("FFmpeg is currently streaming: %s", Path(potential_file).name)
                                    break
                        except (ValueError, IndexError):
                            continue
            except Exception as e:
                LOGGER.debug("Could not check FFmpeg process: %s", e)
            
            # Load playhead state
            LOGGER.info("Loading playhead state...")
            playhead_state = load_playhead_state(force_reload=True)
            LOGGER.info("Playhead state: %s", playhead_state)
            
            # Determine current_index based on FFmpeg state and playhead
            current_index = 0  # Default fallback
            
            if playhead_state and playhead_state.get("current_index") is not None:
                playhead_index = playhead_state.get("current_index", -1)
                playhead_path = playhead_state.get("current_path")
                
                # Priority 1: If FFmpeg is streaming a file, find that file's index
                if ffmpeg_streaming_file:
                    found_ffmpeg_index = None
                    for idx, f in enumerate(files):
                        if f == ffmpeg_streaming_file:
                            found_ffmpeg_index = idx
                            break
                    
                    if found_ffmpeg_index is not None:
                        current_index = found_ffmpeg_index
                        LOGGER.info("FFmpeg is streaming file at index %d, updating playhead to match", current_index)
                        # Update playhead to match what's actually streaming
                        if playhead_index != found_ffmpeg_index or playhead_path != ffmpeg_streaming_file:
                            LOGGER.info("Updating playhead to match FFmpeg state (index %d)", found_ffmpeg_index)
                            update_playhead(ffmpeg_streaming_file, found_ffmpeg_index, playlist_mtime)
                        # FFmpeg is already streaming this file - don't restart it
                        # Skip this iteration and let FFmpeg continue streaming
                        LOGGER.info("FFmpeg is already streaming index %d (%s), skipping restart - will check again after delay", 
                                  current_index, Path(ffmpeg_streaming_file).name)
                        time.sleep(5)
                        continue
                    else:
                        # FFmpeg is streaming a file not in playlist - this shouldn't happen
                        # But if it does, don't restart - let FFmpeg finish
                        LOGGER.warning("FFmpeg streaming file not in playlist: %s, but FFmpeg is running - letting it continue", 
                                     Path(ffmpeg_streaming_file).name)
                        # Don't restart - wait and check again
                        time.sleep(5)
                        continue
                
                # Priority 2: If no FFmpeg running, use playhead logic
                elif 0 <= playhead_index < len(files):
                    entry_at_playhead = files[playhead_index]
                    
                    # Check if playlist has changed - entry at playhead index doesn't match playhead path
                    if playhead_path and entry_at_playhead != playhead_path:
                        # Playlist changed, search for the episode path
                        LOGGER.info("Playlist changed - entry at index %d doesn't match playhead path, searching...", playhead_index)
                        found = False
                        for idx, f in enumerate(files):
                            if f == playhead_path:
                                current_index = idx
                                LOGGER.info("Found playhead episode at new index %d", current_index)
                                found = True
                                break
                        if not found:
                            # Episode path not found in playlist - playhead path is stale
                            # Fix playhead to match the entry at the playhead index
                            LOGGER.warning("Playhead path not found in playlist (stale path), updating playhead to match entry at index %d", playhead_index)
                            if is_episode_entry(entry_at_playhead):
                                # Update playhead to correct path at this index
                                update_playhead(entry_at_playhead, playhead_index, playlist_mtime)
                                current_index = playhead_index
                                LOGGER.info("Updated playhead to correct path at index %d", current_index)
                            else:
                                # Entry at playhead index is not an episode, advance past it
                                LOGGER.info("Entry at playhead index %d is not an episode, advancing", playhead_index)
                                # Check if there's a bumper block marker at the playhead index or right after
                                if playhead_index < len(files) and (is_bumper_block(files[playhead_index]) or is_weather_bumper(files[playhead_index])):
                                    current_index = playhead_index
                                    LOGGER.info("Found bumper block at playhead index %d, starting there", current_index)
                                else:
                                    current_index = playhead_index + 1
                                    if current_index >= len(files):
                                        current_index = 0
                                # Update playhead to new position
                                if current_index < len(files):
                                    new_entry = files[current_index]
                                    if is_episode_entry(new_entry) or is_bumper_block(new_entry) or is_weather_bumper(new_entry):
                                        update_playhead(new_entry if is_episode_entry(new_entry) else "", current_index, playlist_mtime)
                    
                    # If playhead points to a marker but path is an episode, find the episode
                    elif (is_bumper_block(entry_at_playhead) or is_weather_bumper(entry_at_playhead)) and playhead_path:
                        # Search for the episode path
                        for idx, f in enumerate(files):
                            if is_episode_entry(f) and f == playhead_path:
                                current_index = idx
                                LOGGER.info("Playhead pointed to marker, found episode at index %d", current_index)
                                break
                        else:
                            # Episode not found, use playhead index
                            current_index = playhead_index
                    
                    # If playhead points to an episode and matches path, check if FFmpeg is already streaming it
                    elif is_episode_entry(entry_at_playhead) and playhead_path == entry_at_playhead:
                        # Episode at playhead - check if FFmpeg is already streaming it
                        # If FFmpeg is streaming this episode, don't restart it
                        if ffmpeg_streaming_file == entry_at_playhead:
                            LOGGER.info("FFmpeg is already streaming episode at playhead index %d, continuing", playhead_index)
                            # Don't restart - let FFmpeg continue streaming
                            # Skip this iteration and reload playlist to check again
                            time.sleep(5)
                            continue
                        else:
                            # FFmpeg is not streaming this episode - stream it (may have stopped or crashed)
                            LOGGER.info("Episode at playhead index %d - streaming (no FFmpeg detected for this episode, may have stopped)", playhead_index)
                            current_index = playhead_index
                    else:
                        # Default: use playhead index
                        current_index = playhead_index
                else:
                    # Invalid playhead index, start from beginning
                    current_index = 0
                    LOGGER.warning("Invalid playhead index %d, starting from beginning", playhead_index)
            
            # Main loop: process current entry
            if current_index >= len(files):
                current_index = 0
            
            LOGGER.info("Processing entry at index %d", current_index)
            entry = files[current_index]
            LOGGER.info("Entry type: %s", "episode" if is_episode_entry(entry) else "bumper_block" if is_bumper_block(entry) else "other")
            
            # Before streaming, double-check that FFmpeg isn't already streaming this file
            # This prevents restarting episodes/bumpers that are already playing
            if ffmpeg_streaming_file and ffmpeg_streaming_file == entry:
                LOGGER.info("FFmpeg is already streaming this entry (index %d: %s), skipping restart", 
                          current_index, Path(entry).name)
                # Wait a bit and reload playlist to check again
                time.sleep(5)
                continue
            
            # Handle episode
            if is_episode_entry(entry):
                LOGGER.info("=" * 60)
                LOGGER.info("STREAMING EPISODE: %s (index %d)", Path(entry).name, current_index)
                LOGGER.info("=" * 60)
                
                # Pre-generate bumper block for episode after next
                pregenerate_next_bumper_block(current_index, files)
                
                # Reset HLS output for clean episode start
                reset_hls_output(reason="episode_start")
                
                # Record playhead immediately so skip detection doesn't treat us as stale
                try:
                    update_playhead(entry, current_index, playlist_mtime)
                except Exception:
                    pass
                
                # Stream episode
                success = stream_file(entry, current_index, playlist_mtime)
                
                if success:
                    # Episode completed successfully
                    LOGGER.info("Episode completed successfully: %s", Path(entry).name)
                    
                    # Update playhead to next entry BEFORE advancing
                    # This ensures playhead is updated before we advance
                    next_index = current_index + 1
                    if next_index >= len(files):
                        next_index = 0
                    
                    if next_index < len(files):
                        next_entry = files[next_index]
                        # Update playhead to next entry (could be bumper block or episode)
                        if is_bumper_block(next_entry) or is_weather_bumper(next_entry):
                            # Next is a bumper block marker - update playhead to marker
                            update_playhead(next_entry, next_index, playlist_mtime)
                        elif is_episode_entry(next_entry):
                            # Next is an episode - update playhead to episode
                            update_playhead(next_entry, next_index, playlist_mtime)
                    
                    # Mark as watched
                    try:
                        mark_episode_watched(entry)
                    except Exception:
                        pass
                    
                    # Advance to next entry
                    current_index = next_index
                    LOGGER.info("Episode completed, advancing to index %d", current_index)
                else:
                    # Stream failed, skip to next
                    LOGGER.warning("Stream failed, skipping to next")
                    current_index += 1
                    if current_index >= len(files):
                        current_index = 0
                    # Update playhead to new position
                    if current_index < len(files):
                        next_entry = files[current_index]
                        if is_episode_entry(next_entry) or is_bumper_block(next_entry) or is_weather_bumper(next_entry):
                            update_playhead(next_entry if is_episode_entry(next_entry) else "", current_index, playlist_mtime)
            
            # Handle bumper block
            elif is_bumper_block(entry):
                LOGGER.info("=" * 60)
                LOGGER.info("STREAMING BUMPER BLOCK (index %d)", current_index)
                LOGGER.info("=" * 60)
                
                # Record playhead so skip detection matches this marker while bumpers stream
                try:
                    update_playhead(entry, current_index, playlist_mtime)
                except Exception:
                    pass
                
                # Find next episode (the one this bumper block is promoting)
                next_episode_idx = current_index + 1
                while next_episode_idx < len(files) and not is_episode_entry(files[next_episode_idx]):
                    next_episode_idx += 1
                
                if next_episode_idx >= len(files):
                    LOGGER.warning("No episode found after bumper block, skipping")
                    current_index += 1
                    if current_index >= len(files):
                        current_index = 0
                    continue
                
                # Resolve bumper block using unified logic
                block = resolve_bumper_block(next_episode_idx, files)
                
                # If no pre-generated block, try to generate on-demand with timeout
                # But if it takes too long, skip and go straight to the episode
                if not block:
                    LOGGER.info("No pre-generated block found, attempting on-demand generation for %s (will timeout after 20s)", Path(files[next_episode_idx]).name)
                    try:
                        result_queue = queue.Queue(maxsize=1)
                        
                        def generate_block():
                            try:
                                result = resolve_bumper_block(next_episode_idx, files)
                                result_queue.put(('success', result), timeout=1.0)
                            except Exception as e:
                                try:
                                    result_queue.put(('error', e), timeout=1.0)
                                except queue.Full:
                                    pass  # Queue full, main thread will timeout
                        
                        # Start generation in a thread
                        thread = threading.Thread(target=generate_block, daemon=True)
                        thread.start()
                        
                        # Wait for result with timeout
                        try:
                            result_type, result_value = result_queue.get(timeout=20.0)
                            if result_type == 'success':
                                block = result_value
                            else:
                                raise result_value
                        except queue.Empty:
                            LOGGER.warning("Bumper block generation timed out after 20s, skipping bumper block and advancing to episode")
                            # Skip bumper block and advance to episode
                            current_index = next_episode_idx
                            if current_index >= len(files):
                                current_index = 0
                            # Update playhead to episode
                            if current_index < len(files):
                                next_entry = files[current_index]
                                if is_episode_entry(next_entry):
                                    update_playhead(next_entry, current_index, playlist_mtime)
                            continue
                    except Exception as e:
                        LOGGER.warning("Bumper block generation failed: %s, skipping bumper block and advancing to episode", e)
                        # Skip bumper block and advance to episode
                        current_index = next_episode_idx
                        if current_index >= len(files):
                            current_index = 0
                        # Update playhead to episode BEFORE continuing
                        if current_index < len(files):
                            next_entry = files[current_index]
                            if is_episode_entry(next_entry):
                                LOGGER.info("Updating playhead to episode at index %d: %s", current_index, Path(next_entry).name)
                                update_playhead(next_entry, current_index, playlist_mtime)
                        # Continue loop to process the episode
                        continue
                
                if block and block.bumpers:
                    # Validate all bumper files exist before starting
                    missing_bumpers = [b for b in block.bumpers if not os.path.exists(b)]
                    if missing_bumpers:
                        LOGGER.error("Missing bumper files in block: %s", [Path(b).name for b in missing_bumpers])
                        # Try to skip bumper block and go to episode
                        current_index = next_episode_idx
                        if current_index >= len(files):
                            current_index = 0
                        if current_index < len(files):
                            next_entry = files[current_index]
                            if is_episode_entry(next_entry):
                                update_playhead(next_entry, current_index, playlist_mtime)
                        continue
                    
                    # Stream all bumpers sequentially
                    bumper_success = True
                    # Use next_episode_idx for skip detection during bumper streaming
                    # This prevents skip detection from interrupting bumper playback
                    bumper_stream_index = next_episode_idx if next_episode_idx < len(files) else current_index
                    
                    LOGGER.info("Starting bumper block playback: %d bumpers", len(block.bumpers))
                    for i, bumper_path in enumerate(block.bumpers):
                        LOGGER.info("Streaming bumper %d/%d: %s", i+1, len(block.bumpers), Path(bumper_path).name)
                        # Only reset playlist before first bumper, subsequent bumpers append seamlessly
                        if i == 0:
                            reset_hls_output(reason="bumper_block_start")
                        # Disable skip detection during bumper streaming to prevent false interrupts
                        # Bumpers are short and should complete without interruption
                        if not stream_file(bumper_path, bumper_stream_index, playlist_mtime, disable_skip_detection=True):
                            LOGGER.error("Bumper stream failed: %s", bumper_path)
                            bumper_success = False
                            break
                        else:
                            LOGGER.info("✓ Bumper %d/%d completed successfully", i+1, len(block.bumpers))
                    
                    # Clean up original bumpers after successful streaming
                    if bumper_success and hasattr(block, '_cleanup_bumpers'):
                        cleanup_bumpers(block._cleanup_bumpers)
                    
                    if bumper_success:
                        LOGGER.info("✓✓✓ BUMPER BLOCK COMPLETED SUCCESSFULLY ✓✓✓")
                        try:
                            # Advance to the episode that this bumper block was promoting
                            current_index = next_episode_idx
                            if current_index >= len(files):
                                current_index = 0
                            
                            # Update playhead to next episode BEFORE continuing loop
                            # This ensures the playhead is correct when the loop reloads the playlist
                            LOGGER.info("Bumper block completed, advancing to episode at index %d", current_index)
                            if current_index < len(files):
                                next_entry = files[current_index]
                                if is_episode_entry(next_entry):
                                    LOGGER.info("Updating playhead to episode at index %d: %s", current_index, Path(next_entry).name)
                                    update_playhead(next_entry, current_index, playlist_mtime)
                                else:
                                    LOGGER.warning("Next entry at index %d is not an episode, searching for episode...", current_index)
                                    # Skip to next episode
                                    skip_idx = current_index + 1
                                    while skip_idx < len(files) and not is_episode_entry(files[skip_idx]):
                                        skip_idx += 1
                                    if skip_idx < len(files):
                                        LOGGER.info("Found episode at index %d: %s", skip_idx, Path(files[skip_idx]).name)
                                        update_playhead(files[skip_idx], skip_idx, playlist_mtime)
                                        current_index = skip_idx
                                    else:
                                        LOGGER.warning("No episode found after bumper block, wrapping to start")
                                        current_index = 0
                                        if len(files) > 0 and is_episode_entry(files[0]):
                                            update_playhead(files[0], 0, playlist_mtime)
                            
                            # IMPORTANT: Break out of the loop iteration and let it reload the playlist
                            # This ensures the playhead update is visible and prevents replaying the bumper block
                            LOGGER.info("Bumper block complete, breaking to reload playlist with updated playhead")
                        except Exception as e:
                            LOGGER.error("Failed to update playhead after bumper block: %s", e, exc_info=True)
                        # Break to reload playlist with updated playhead
                        break
                    else:
                        LOGGER.warning("Bumper block failed, skipping to next episode")
                        current_index = next_episode_idx
                        if current_index >= len(files):
                            current_index = 0
                        # Update playhead and break to reload playlist
                        if current_index < len(files):
                            next_entry = files[current_index]
                            if is_episode_entry(next_entry):
                                update_playhead(next_entry, current_index, playlist_mtime)
                        break
                else:
                    LOGGER.warning("Failed to resolve bumper block, skipping to next episode")
                    current_index = next_episode_idx
                    if current_index >= len(files):
                        current_index = 0
                    # Update playhead and break to reload playlist
                    if current_index < len(files):
                        next_entry = files[current_index]
                        if is_episode_entry(next_entry):
                            update_playhead(next_entry, current_index, playlist_mtime)
                    break
            
            # Skip other markers
            else:
                LOGGER.debug("Skipping marker: %s", entry)
                current_index += 1
                if current_index >= len(files):
                    current_index = 0
            
            # Small delay to prevent tight loop
            time.sleep(0.1)
            
        except KeyboardInterrupt:
            LOGGER.info("Interrupted by user")
            break
        except Exception as e:
            LOGGER.error("Error in streaming loop: %s", e, exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    def signal_handler(signum, frame):
        LOGGER.info("Received signal %d, cleaning up...", signum)
        cleanup_on_exit()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Acquire lock
    if not acquire_streamer_lock():
        LOGGER.error("Another streamer is already running. Exiting.")
        sys.exit(1)
    
    # Clean up orphaned processes
    cleanup_orphaned_ffmpeg_processes()
    cleanup_orphaned_ffmpeg_processes()
    time.sleep(1)
    
    # Write PID
    try:
        HLS_DIR.mkdir(parents=True, exist_ok=True)
        with STREAMER_PID_FILE.open("w") as f:
            f.write(str(os.getpid()) + "\n")
    except Exception:
        pass
    
    LOGGER.info("Streamer lock acquired (PID: %d)", os.getpid())
    
    # Ensure up-next bumper backgrounds are generated
    try:
        LOGGER.info("Checking for up-next bumper backgrounds...")
        repo_root = Path(__file__).resolve().parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        
        # Run background generation script (non-blocking, won't regenerate if exists)
        bg_script = repo_root / "scripts" / "bumpers" / "generate_up_next_backgrounds.py"
        if bg_script.exists():
            result = subprocess.run(
                [sys.executable, str(bg_script)],
                capture_output=True,
                timeout=600,  # 10 minute timeout
                cwd=str(repo_root)
            )
            if result.returncode == 0:
                LOGGER.info("Up-next bumper backgrounds ready")
            else:
                LOGGER.warning("Background generation had issues (may already exist): %s", result.stderr.decode()[:200])
        else:
            LOGGER.warning("Background generation script not found at %s", bg_script)
    except Exception as e:
        LOGGER.warning("Failed to check/generate backgrounds: %s (continuing anyway)", e)
    
    # Start pre-generation thread
    try:
        from server.bumper_block import get_generator
        generator = get_generator()
        generator.start_pregen_thread()
        LOGGER.info("Started bumper block pre-generation")
    except Exception as e:
        LOGGER.warning("Failed to start pre-generation: %s", e)
    
    try:
        run_stream()
    finally:
        cleanup_on_exit()

