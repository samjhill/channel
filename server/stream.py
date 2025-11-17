#!/usr/bin/env python3

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional

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
_video_height_cache: Dict[str, Optional[int]] = {}


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
        )
        height_str = result.stdout.strip()
        height = int(height_str) if height_str else None
    except (subprocess.CalledProcessError, ValueError):
        height = None

    # Cache the result (even if None to avoid repeated failures)
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
        print(f"ERROR: File not found: {src}", flush=True)
        return False

    if not os.path.isfile(src):
        print(f"ERROR: Path is not a file: {src}", flush=True)
        return False

    print(f"Streaming: {src}", flush=True)
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
        "6000k",
        "-g",
        "60",
        "-sc_threshold",
        "0",
        "-force_key_frames",
        "expr:gte(t,n_forced*6)",
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
        "30",
        "-hls_flags",
        "delete_segments+append_list+omit_endlist+discont_start",
        "-hls_segment_type",
        "mpegts",
        "-hls_segment_filename",
        "/app/hls/stream%04d.ts",
        OUTPUT,
    ]

    # Start FFmpeg as a subprocess so we can monitor it
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

                # Debug logging (can be removed later)
                if paths_differ:
                    print(
                        f"DEBUG: Playhead check - src={src}, playhead={playhead_path}, normalized_src={normalized_src if _normalize_path else 'N/A'}, normalized_playhead={normalized_playhead if _normalize_path else 'N/A'}, paths_differ={paths_differ}, mtime_match={abs(playhead_mtime - playlist_mtime) < 0.001}",
                        flush=True,
                    )

                # If playhead points to a different file, skip was triggered
                if paths_differ:
                    # Verify this is a valid skip (same playlist, different file)
                    # Use a more lenient mtime check (within 1 second) to handle filesystem timing differences
                    mtime_match = abs(playhead_mtime - playlist_mtime) < 1.0

                    # If mtime doesn't match but playhead was recently updated, still allow skip
                    # Check if playhead was updated in the last 10 seconds (window for Docker sync delays)
                    playhead_updated_at = playhead_state.get("updated_at", 0.0)
                    current_time_check = time.time()
                    recent_update = (
                        playhead_updated_at > 0
                        and (current_time_check - playhead_updated_at) < 10.0
                    )

                    # Allow skip if mtime matches OR if playhead was recently updated
                    # This handles cases where playlists are out of sync but skip was just triggered
                    if mtime_match or recent_update:
                        print(
                            f"Skip detected: interrupting {src} to jump to {playhead_path} (mtime_match={mtime_match}, recent_update={recent_update}, updated_at={playhead_updated_at}, current_time={current_time_check})",
                            flush=True,
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
                        print(
                            f"DEBUG: Skip check failed - mtime_match={mtime_match}, recent_update={recent_update}, playhead_mtime={playhead_mtime}, playlist_mtime={playlist_mtime}, updated_at={playhead_updated_at}, current_time={current_time_check}",
                            flush=True,
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
            print(f"Stream interrupted: {src}", flush=True)
            return False
        else:
            print(
                f"ERROR: FFmpeg failed with return code {returncode} for {src}",
                flush=True,
            )
            if stderr_output:
                print(f"FFmpeg stderr: {stderr_output[:500]}", flush=True)
            return False

    return True


def record_playhead(src: str, index: int, playlist_mtime: float) -> None:
    """Record playhead state, but don't overwrite if it was recently updated externally (skip command)."""
    # Check if playhead was recently updated externally (within last 2 seconds)
    # Only skip if it points to a different file (skip command), not if it's the same (normal playback)
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
                print(
                    f"Skipping playhead record - was recently updated externally to different file (age: {time.time() - existing_updated_at:.2f}s)",
                    flush=True,
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

    while True:
        try:
            files, playlist_mtime = load_playlist()
        except FileNotFoundError as exc:
            print(exc, flush=True)
            time.sleep(5)
            continue

        if not files:
            print("Playlist empty, waiting for media files...", flush=True)
            time.sleep(10)
            continue

        # Validate playlist entries are valid files before processing
        valid_files = []
        for file_path in files:
            if os.path.exists(file_path) and os.path.isfile(file_path):
                valid_files.append(file_path)
            else:
                print(
                    f"WARNING: Skipping invalid playlist entry: {file_path}", flush=True
                )

        if not valid_files:
            print("No valid files in playlist, waiting...", flush=True)
            time.sleep(10)
            continue

        files = valid_files

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

            # Determine the normal next file to stream
            normal_next_src = files[next_index]

            # Check if playhead has been updated externally (e.g., by skip API)
            # This allows the skip button to work by jumping to the next episode
            # Only treat as external update if playhead points to a DIFFERENT file than normal flow
            # AND it's not the file we just finished streaming (to avoid loops)
            playhead_state = load_playhead_state()
            playhead_updated_externally = False

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
                recent_update = (
                    playhead_updated_at > 0
                    and (time.time() - playhead_updated_at) < 10.0
                )

                # Only jump if playhead differs from normal flow AND was recently updated (skip command)
                # AND it's not the file we just finished streaming
                if (
                    playhead_matches
                    and playhead_differs_from_normal
                    and not playhead_is_last_played
                    and (mtime_match or recent_update)
                ):
                    next_index = matching_index
                    src = files[
                        matching_index
                    ]  # Use the actual file path from the playlist
                    playhead_updated_externally = True
                    print(
                        f"Playhead updated externally: jumping to {src} (index {next_index})",
                        flush=True,
                    )

            if not playhead_updated_externally:
                # Normal flow - use calculated next_index
                src = normal_next_src

            # Only record playhead if it wasn't updated externally (to avoid overwriting skip commands)
            # If playhead was updated externally, the skip API already set it correctly
            if not playhead_updated_externally:
                record_playhead(src, next_index, playlist_mtime)

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
                            print(
                                f"Jumping to skipped episode: {src} (index {next_index})",
                                flush=True,
                            )
                            # Continue to next iteration to stream the skipped-to file
                            continue
                        else:
                            print(
                                f"DEBUG: Skip target not found or invalid - matching_index={matching_index}, mtime_match={mtime_match}, recent_update={recent_update}",
                                flush=True,
                            )

            last_played = src

            # Mark episode as watched only if streaming completed successfully (not interrupted)
            if streaming_succeeded and is_episode_entry(src) and not stream_was_skipped:
                mark_episode_watched(src)
            elif not streaming_succeeded and not stream_was_skipped:
                print(
                    f"WARNING: Skipping watch progress update for failed stream: {src}",
                    flush=True,
                )

            try:
                files, playlist_mtime = load_playlist()
            except FileNotFoundError as exc:
                print(exc, flush=True)
                time.sleep(5)
                break

            if not files:
                print("Playlist empty after update, waiting...", flush=True)
                time.sleep(10)
                break

            # Advance to next index after successful streaming
            # This ensures we don't replay the same file
            if streaming_succeeded and not stream_was_skipped:
                # Optimize: only search if we need to find the next position
                # If playlist didn't change, just increment
                if next_index < len(files) and files[next_index] == last_played:
                    next_index += 1
                else:
                    try:
                        next_index = files.index(last_played) + 1
                    except ValueError:
                        next_index = 0

                # Wrap around if we've reached the end
                if next_index >= len(files):
                    next_index = 0


if __name__ == "__main__":
    run_stream()
