"""Tests for stream.py module."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Import stream module functions
from server.stream import (
    is_bumper_block,
    is_weather_bumper,
    load_playlist,
    stream_file,
    reset_hls_output,
    cleanup_bumpers,
    _should_include_weather,
    _get_up_next_bumper,
    resolve_bumper_block,
)


@pytest.mark.unit
def test_is_bumper_block():
    """Test bumper block marker detection."""
    assert is_bumper_block("BUMPER_BLOCK") is True
    assert is_bumper_block("bumper_block") is True
    assert is_bumper_block("  BUMPER_BLOCK  ") is True
    assert is_bumper_block("/path/to/episode.mp4") is False
    assert is_bumper_block("") is False


@pytest.mark.unit
def test_is_weather_bumper():
    """Test weather bumper marker detection."""
    assert is_weather_bumper("WEATHER_BUMPER") is True
    assert is_weather_bumper("weather_bumper") is True
    assert is_weather_bumper("/bumpers/weather/test.mp4") is True
    assert is_weather_bumper("/path/to/episode.mp4") is False


@pytest.mark.unit
def test_load_playlist(temp_dir: Path, monkeypatch):
    """Test loading playlist."""
    playlist_file = temp_dir / "playlist.txt"
    monkeypatch.setenv("CHANNEL_PLAYLIST_PATH", str(playlist_file))

    # Create playlist with entries
    entries = [
        "/path/to/episode1.mp4",
        "/path/to/episode2.mp4",
        "",  # Empty line should be filtered
        "/path/to/episode3.mp4",
    ]
    playlist_file.write_text("\n".join(entries))

    import server.playlist_service as ps_module

    ps_module._playlist_path_cache = None
    ps_module._playlist_cache = None

    files, mtime = load_playlist()
    assert len(files) == 3
    assert "/path/to/episode1.mp4" in files
    assert "" not in files


@pytest.mark.unit
@patch("subprocess.Popen")
@patch("server.stream.load_playhead_state")
@patch("os.path.exists")
@patch("os.path.isfile")
def test_stream_file_success(
    mock_isfile: MagicMock,
    mock_exists: MagicMock,
    mock_load_playhead: MagicMock,
    mock_popen: MagicMock,
    temp_dir: Path,
):
    """Test successful file streaming."""
    mock_exists.return_value = True
    mock_isfile.return_value = True

    # Mock playhead state (no skip)
    mock_load_playhead.return_value = {
        "current_path": "/path/to/video.mp4",
        "current_index": 0,
    }

    # Mock FFmpeg process - needs to stay running initially, then finish successfully
    mock_process = MagicMock()
    mock_process.poll.side_effect = [None, None, 0]  # None = still running, then 0 = finished
    mock_process.returncode = 0  # Success
    mock_process.stderr = None
    mock_popen.return_value = mock_process

    # Mock time.sleep to speed up test
    with patch("server.stream.BUG_IMAGE_PATH") as mock_bug_path, \
         patch("server.stream.time.sleep"), \
         patch("server.stream.os.path.exists") as mock_seg_exists:
        mock_bug_path.exists.return_value = False
        mock_seg_exists.return_value = True  # Segments exist
        result = stream_file("/path/to/video.mp4", 0, 1234567890.0)
        assert result is True


@pytest.mark.unit
@patch("os.path.exists")
@patch("os.path.isfile")
def test_stream_file_not_found(mock_isfile: MagicMock, mock_exists: MagicMock):
    """Test streaming non-existent file."""
    mock_exists.return_value = False
    mock_isfile.return_value = False

    result = stream_file("/path/to/nonexistent.mp4", 0, 1234567890.0)
    assert result is False


@pytest.mark.unit
@patch("os.path.exists")
@patch("os.path.isfile")
def test_stream_file_not_a_file(mock_isfile: MagicMock, mock_exists: MagicMock):
    """Test streaming a path that's not a file."""
    mock_exists.return_value = True
    mock_isfile.return_value = False  # Not a file

    result = stream_file("/path/to/directory", 0, 1234567890.0)
    assert result is False


@pytest.mark.unit
@patch("subprocess.Popen")
@patch("server.stream.load_playhead_state")
@patch("os.path.exists")
@patch("os.path.isfile")
def test_stream_file_ffmpeg_failure(
    mock_isfile: MagicMock,
    mock_exists: MagicMock,
    mock_load_playhead: MagicMock,
    mock_popen: MagicMock,
):
    """Test streaming with FFmpeg failure."""
    mock_exists.return_value = True
    mock_isfile.return_value = True

    mock_load_playhead.return_value = {
        "current_path": "/path/to/video.mp4",
        "current_index": 0,
    }

    # Mock FFmpeg process that fails
    mock_process = MagicMock()
    mock_process.poll.return_value = 1  # Process finished with error
    mock_process.returncode = 1  # Failure
    mock_process.stderr = MagicMock()
    mock_process.stderr.read.return_value = b"FFmpeg error"
    mock_popen.return_value = mock_process

    with patch("server.stream.BUG_IMAGE_PATH") as mock_bug_path:
        mock_bug_path.exists.return_value = False
        result = stream_file("/path/to/video.mp4", 0, 1234567890.0)
        assert result is False
