#!/usr/bin/env python3
"""
Clean streaming server rewrite.
Simple state machine: Episode -> Bumper Block -> Episode
Pre-generates bumper blocks before episodes finish.
"""

from __future__ import annotations

import contextlib
import fcntl
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    try:
        from playlist_service import _normalize_path
    except ImportError:
        _normalize_path = None
except ImportError:
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
    try:
        from server.playlist_service import _normalize_path
    except ImportError:
        _normalize_path = None

# Constants
BUMPER_BLOCK_MARKER = "BUMPER_BLOCK"
HLS_DIR = Path("/app/hls")
OUTPUT = HLS_DIR / "stream.m3u8"
BUG_IMAGE_PATH = Path("/app/assets/branding/hbn_logo_bug.png")
STREAMER_LOCK_FILE = HLS_DIR / "streamer.lock"
STREAMER_PID_FILE = HLS_DIR / "streamer.pid"

_lock_file_handle = None


def is_bumper_block(entry: str) -> bool:
    """Check if entry is a bumper block marker."""
    return entry.strip() == BUMPER_BLOCK_MARKER


def is_weather_bumper(entry: str) -> bool:
    """Check if entry is a weather bumper marker."""
    return entry.strip() == "WEATHER_BUMPER"


def load_playlist() -> tuple[List[str], float]:
    """Load playlist and return (files, mtime)."""
    playlist_path = resolve_playlist_path()
    if not playlist_path.exists():
        raise FileNotFoundError(f"Playlist not found: {playlist_path}")
    
    mtime = playlist_path.stat().st_mtime
    files = load_playlist_entries()
    return files, mtime


def reset_hls_output(reason: str = "") -> None:
    """Reset HLS output for clean transition."""
    try:
        if HLS_DIR.exists():
            for ts_file in HLS_DIR.glob("stream*.ts"):
                with contextlib.suppress(OSError):
                    ts_file.unlink()
        with open(OUTPUT, "w", encoding="utf-8") as playlist:
            playlist.write("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:6\n")
        if reason:
            LOGGER.info("Reset HLS output (%s)", reason)
    except Exception as exc:
        LOGGER.warning("Failed to reset HLS output: %s", exc)


def stream_file(src: str, index: int, playlist_mtime: float) -> bool:
    """Stream a single file (episode or bumper) to HLS."""
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
        "-hls_flags", "delete_segments+append_list+omit_endlist+discont_start+program_date_time",
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
        time.sleep(0.5)
        if process.poll() is not None:
            LOGGER.error("FFmpeg exited immediately with return code %d", process.returncode)
            return False
        
        # Wait for process to complete
        while process.poll() is None:
            # Check for skip command
            playhead_state = load_playhead_state(force_reload=True)
            if playhead_state:
                playhead_index = playhead_state.get("current_index", -1)
                if playhead_index >= 0 and playhead_index != index:
                    LOGGER.info("Skip detected, interrupting stream")
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    return False
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
    """Render a weather bumper just-in-time for playback."""
    try:
        from scripts.bumpers.render_weather_bumper import render_weather_bumper
    except ImportError:
        import sys
        repo_root = Path(__file__).resolve().parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from scripts.bumpers.render_weather_bumper import render_weather_bumper
    
    temp_dir = HLS_DIR / "weather_temp"
    temp_dir.mkdir(exist_ok=True)
    out_path = temp_dir / f"weather_{int(time.time())}.mp4"
    
    success = render_weather_bumper(str(out_path))
    if success and out_path.exists():
        return str(out_path)
    return None


def resolve_bumper_block(next_episode_index: int, files: List[str]) -> Optional[Any]:
    """Resolve a bumper block for the next episode."""
    try:
        from server.bumper_block import get_generator
        from server.generate_playlist import (
            find_existing_bumper,
            extract_episode_metadata,
            infer_show_title_from_path,
            load_weather_config,
            ensure_bumper,
        )
        
        if next_episode_index >= len(files):
            return None
        
        next_episode = files[next_episode_index]
        if not os.path.exists(next_episode):
            return None
        
        # Get up-next bumper
        show_label = infer_show_title_from_path(next_episode)
        metadata = extract_episode_metadata(next_episode)
        up_next_bumper = find_existing_bumper(show_label, metadata)
        
        if not up_next_bumper:
            # Try to generate it
            try:
                from server.generate_playlist import ensure_bumper
                up_next_bumper = ensure_bumper(show_label, metadata)
            except Exception:
                LOGGER.warning("Could not get up-next bumper for %s", show_label)
                return None
        
        # Get weather bumper if enabled
        weather_bumper = None
        try:
            weather_cfg = load_weather_config()
            if weather_cfg.get("enabled", False):
                weather_bumper = _render_weather_bumper_jit()
        except Exception:
            pass
        
        # Generate bumper block
        generator = get_generator()
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
    """Pre-generate bumper block for the episode after next."""
    try:
        from server.bumper_block import get_generator
        from server.generate_playlist import (
            find_existing_bumper,
            extract_episode_metadata,
            infer_show_title_from_path,
        )
        
        # Find next episode after current
        next_episode_idx = current_index + 1
        while next_episode_idx < len(files) and not is_episode_entry(files[next_episode_idx]):
            next_episode_idx += 1
        
        if next_episode_idx >= len(files):
            return
        
        # Find episode after that (for pre-generation)
        episode_after_next = next_episode_idx + 1
        while episode_after_next < len(files) and not is_episode_entry(files[episode_after_next]):
            episode_after_next += 1
        
        if episode_after_next >= len(files):
            return
        
        next_episode = files[episode_after_next]
        if not os.path.exists(next_episode):
            return
        
        # Get up-next bumper
        show_label = infer_show_title_from_path(next_episode)
        metadata = extract_episode_metadata(next_episode)
        up_next_bumper = find_existing_bumper(show_label, metadata)
        
        if not up_next_bumper:
            return
        
        # Queue for pre-generation
        generator = get_generator()
        if not generator._pregen_thread or not generator._pregen_thread.is_alive():
            generator.start_pregen_thread()
        
        block_spec = {
            "up_next_bumper": up_next_bumper,
            "sassy_card": None,
            "network_bumper": None,
            "weather_bumper": None,
        }
        generator.queue_pregen(block_spec)
        LOGGER.debug("Queued bumper block pre-generation for %s", Path(next_episode).name)
    except Exception as e:
        LOGGER.debug("Failed to pre-generate bumper block: %s", e)


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
            files, playlist_mtime = load_playlist()
            
            # Filter to valid files only
            valid_files = []
            for f in files:
                if is_bumper_block(f) or is_weather_bumper(f):
                    valid_files.append(f)
                elif os.path.exists(f):
                    valid_files.append(f)
            
            if not valid_files:
                LOGGER.info("No valid files in playlist, waiting...")
                time.sleep(10)
                continue
            
            files = valid_files
            
            # Get current position from playhead
            # If playhead points to a marker, find the actual episode
            playhead_state = load_playhead_state(force_reload=True)
            if playhead_state and playhead_state.get("current_index") is not None:
                playhead_index = playhead_state.get("current_index", -1)
                playhead_path = playhead_state.get("current_path")
                
                if 0 <= playhead_index < len(files):
                    entry_at_playhead = files[playhead_index]
                    # If playhead points to a marker but path is an episode, find the episode
                    if (is_bumper_block(entry_at_playhead) or is_weather_bumper(entry_at_playhead)) and playhead_path:
                        # Search for the episode path
                        for idx, f in enumerate(files):
                            if is_episode_entry(f) and f == playhead_path:
                                current_index = idx
                                LOGGER.info("Playhead pointed to marker, found episode at index %d", current_index)
                                break
                        else:
                            # Episode not found, use playhead index
                            current_index = playhead_index
                    else:
                        current_index = playhead_index
            
            # Main loop: process current entry
            if current_index >= len(files):
                current_index = 0
            
            entry = files[current_index]
            
            # Handle episode
            if is_episode_entry(entry):
                LOGGER.info("=" * 60)
                LOGGER.info("STREAMING EPISODE: %s (index %d)", Path(entry).name, current_index)
                LOGGER.info("=" * 60)
                
                # Pre-generate bumper block for episode after next
                pregenerate_next_bumper_block(current_index, files)
                
                # Reset HLS output for clean episode start
                reset_hls_output(reason="episode_start")
                
                # Stream episode
                success = stream_file(entry, current_index, playlist_mtime)
                
                if success:
                    # Update playhead
                    update_playhead(entry, current_index, playlist_mtime)
                    
                    # Advance to next entry
                    current_index += 1
                    if current_index >= len(files):
                        current_index = 0
                    
                    # Mark as watched
                    try:
                        mark_episode_watched(entry)
                    except Exception:
                        pass
                else:
                    # Stream failed, skip to next
                    LOGGER.warning("Stream failed, skipping to next")
                    current_index += 1
                    if current_index >= len(files):
                        current_index = 0
            
            # Handle bumper block
            elif is_bumper_block(entry):
                LOGGER.info("=" * 60)
                LOGGER.info("STREAMING BUMPER BLOCK (index %d)", current_index)
                LOGGER.info("=" * 60)
                
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
                
                # Resolve bumper block (try pre-generated first, then generate on-demand)
                block = None
                try:
                    from server.bumper_block import get_generator
                    generator = get_generator()
                    
                    # Try to get pre-generated block
                    next_episode = files[next_episode_idx]
                    from server.generate_playlist import (
                        find_existing_bumper,
                        extract_episode_metadata,
                        infer_show_title_from_path,
                    )
                    show_label = infer_show_title_from_path(next_episode)
                    metadata = extract_episode_metadata(next_episode)
                    up_next_bumper = find_existing_bumper(show_label, metadata)
                    
                    if up_next_bumper:
                        block = generator.get_pregenerated_block(
                            up_next_bumper=up_next_bumper,
                            sassy_card=None,
                            network_bumper=None,
                            weather_bumper=None,
                        )
                except Exception as e:
                    LOGGER.debug("Failed to get pre-generated block: %s", e)
                
                # If no pre-generated block, generate on-demand
                if not block:
                    block = resolve_bumper_block(next_episode_idx, files)
                
                if block and block.bumpers:
                    # Reset HLS output for clean bumper start
                    reset_hls_output(reason="bumper_block")
                    
                    # Stream all bumpers sequentially
                    bumper_success = True
                    for bumper_path in block.bumpers:
                        if not os.path.exists(bumper_path):
                            LOGGER.warning("Bumper file missing: %s", bumper_path)
                            continue
                        
                        LOGGER.info("Streaming bumper: %s", Path(bumper_path).name)
                        if not stream_file(bumper_path, current_index, playlist_mtime):
                            LOGGER.warning("Bumper stream failed: %s", bumper_path)
                            bumper_success = False
                            break
                    
                    if bumper_success:
                        LOGGER.info("✓✓✓ BUMPER BLOCK COMPLETED SUCCESSFULLY ✓✓✓")
                        # Advance past bumper block to next episode
                        current_index += 1
                        if current_index >= len(files):
                            current_index = 0
                    else:
                        LOGGER.warning("Bumper block failed, skipping to next episode")
                        current_index = next_episode_idx
                        if current_index >= len(files):
                            current_index = 0
                else:
                    LOGGER.warning("Failed to resolve bumper block, skipping to next episode")
                    current_index = next_episode_idx
                    if current_index >= len(files):
                        current_index = 0
            
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

