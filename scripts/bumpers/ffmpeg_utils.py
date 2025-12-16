"""
Shared utilities for FFmpeg operations in bumper generation.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional


def run_ffmpeg(
    cmd: list[str],
    timeout: Optional[float] = 300.0,
    description: str = "FFmpeg operation",
) -> None:
    """
    Run an FFmpeg command with proper error handling and logging.

    Args:
        cmd: FFmpeg command as a list of arguments
        timeout: Maximum time to wait in seconds (default 5 minutes)
        description: Description of the operation for error messages

    Raises:
        RuntimeError: If FFmpeg fails or times out
    """
    try:
        result = subprocess.run(
            cmd,
            check=False,  # We'll check manually to capture output
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            error_msg = f"{description} failed with return code {result.returncode}"
            if result.stderr:
                # Include last 1000 chars of stderr (most relevant errors are at the end)
                stderr_preview = result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr
                error_msg += f"\nFFmpeg stderr (last 1000 chars):\n{stderr_preview}"
            if result.stdout:
                stdout_preview = result.stdout[-500:] if len(result.stdout) > 500 else result.stdout
                error_msg += f"\nFFmpeg stdout (last 500 chars):\n{stdout_preview}"
            raise RuntimeError(error_msg)

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{description} timed out after {timeout} seconds")
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found in PATH. Please install FFmpeg.")


def validate_video_file(video_path: Path, min_duration_sec: float = 0.5) -> bool:
    """
    Validate that a video file exists, is readable, and has valid content.

    Args:
        video_path: Path to the video file to validate
        min_duration_sec: Minimum expected duration in seconds

    Returns:
        True if video is valid, False otherwise
    """
    if not video_path.exists():
        print(f"[Validation] Video file does not exist: {video_path}", file=sys.stderr)
        return False

    if video_path.stat().st_size == 0:
        print(f"[Validation] Video file is empty: {video_path}", file=sys.stderr)
        return False

    # Use ffprobe to check if the video is valid
    try:
        probe_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = subprocess.run(
            probe_cmd,
            capture_output=True,
            text=True,
            timeout=10.0,
        )

        if result.returncode != 0:
            print(
                f"[Validation] ffprobe failed for {video_path}: {result.stderr}",
                file=sys.stderr,
            )
            return False

        try:
            duration = float(result.stdout.strip())
            if duration < min_duration_sec:
                print(
                    f"[Validation] Video duration ({duration:.2f}s) is shorter than "
                    f"expected minimum ({min_duration_sec:.2f}s): {video_path}",
                    file=sys.stderr,
                )
                return False
        except (ValueError, AttributeError):
            print(
                f"[Validation] Could not parse video duration from ffprobe output: {video_path}",
                file=sys.stderr,
            )
            return False

    except subprocess.TimeoutExpired:
        print(
            f"[Validation] ffprobe timed out for {video_path}",
            file=sys.stderr,
        )
        return False
    except FileNotFoundError:
        # ffprobe not available, skip validation but warn
        print(
            "[Validation] ffprobe not found, skipping video validation",
            file=sys.stderr,
        )
        return True  # Assume valid if we can't check

    return True


def validate_frame_sequence(
    frame_dir: Path, expected_count: int, pattern: str = "frame_%04d.png"
) -> bool:
    """
    Validate that all expected frames exist in the frame directory.

    Args:
        frame_dir: Directory containing frames
        expected_count: Expected number of frames
        pattern: Frame filename pattern (e.g., "frame_%04d.png")

    Returns:
        True if all frames exist, False otherwise
    """
    missing_frames = []
    for idx in range(expected_count):
        # Convert pattern like "frame_%04d.png" to actual filename
        frame_name = pattern % idx
        frame_path = frame_dir / frame_name
        if not frame_path.exists():
            missing_frames.append(frame_name)

    if missing_frames:
        print(
            f"[Validation] Missing {len(missing_frames)} frames out of {expected_count}: "
            f"{missing_frames[:5]}{'...' if len(missing_frames) > 5 else ''}",
            file=sys.stderr,
        )
        return False

    return True
