"""Tests for stream.py module."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Import stream module functions
from server.stream import (
    build_overlay_args,
    format_number,
    load_playlist,
    overlay_position_expr,
    probe_video_height,
    resolve_assets_root,
    stream_file,
)


@pytest.mark.unit
def test_resolve_assets_root(monkeypatch):
    """Test resolving assets root directory."""
    # Test with environment variable
    test_path = "/custom/assets"
    monkeypatch.setenv("HBN_ASSETS_ROOT", test_path)
    result = resolve_assets_root()
    assert result == test_path
    
    # Test without environment variable (will use default or fallback)
    monkeypatch.delenv("HBN_ASSETS_ROOT", raising=False)
    result = resolve_assets_root()
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.unit
def test_format_number():
    """Test number formatting."""
    assert format_number(1.0) == "1"
    assert format_number(1.5) == "1.5"
    assert format_number(0.8) == "0.8"
    assert format_number(0.1234) == "0.1234"
    assert format_number(0.0) == "0"


@pytest.mark.unit
def test_overlay_position_expr():
    """Test overlay position expression generation."""
    x, y = overlay_position_expr("top-left", 40)
    assert x == "40"
    assert y == "40"
    
    x, y = overlay_position_expr("top-right", 40)
    assert "main_w-overlay_w-40" in x
    assert y == "40"
    
    x, y = overlay_position_expr("bottom-left", 40)
    assert x == "40"
    assert "main_h-overlay_h-40" in y
    
    x, y = overlay_position_expr("bottom-right", 40)
    assert "main_w-overlay_w-40" in x
    assert "main_h-overlay_h-40" in y
    
    # Default to top-right for invalid position
    x, y = overlay_position_expr("invalid", 40)
    assert "main_w-overlay_w-40" in x
    assert y == "40"


@pytest.mark.unit
@patch("subprocess.run")
def test_probe_video_height(mock_run: MagicMock):
    """Test video height probing."""
    # Mock successful ffprobe call
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "1080"
    mock_run.return_value = mock_result
    
    height = probe_video_height("/path/to/video.mp4")
    assert height == 1080
    mock_run.assert_called_once()
    
    # Test caching
    height2 = probe_video_height("/path/to/video.mp4")
    assert height2 == 1080
    # Should use cache, so only one call
    assert mock_run.call_count == 1


@pytest.mark.unit
@patch("subprocess.run")
def test_probe_video_height_failure(mock_run: MagicMock):
    """Test video height probing with failure."""
    # Mock failed ffprobe call
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_run.side_effect = subprocess.CalledProcessError(1, "ffprobe")
    
    # Clear cache first
    import server.stream as stream_module
    if "/path/to/video.mp4" in stream_module._video_height_cache:
        del stream_module._video_height_cache["/path/to/video.mp4"]
    
    height = probe_video_height("/path/to/video.mp4")
    assert height is None


@pytest.mark.unit
@patch("os.path.isfile")
def test_build_overlay_args(mock_isfile: MagicMock):
    """Test building overlay arguments."""
    # Test with bug image file
    mock_isfile.return_value = True
    args, has_overlay = build_overlay_args(1080)
    assert has_overlay is True
    assert "-loop" in args
    assert "-filter_complex" in args
    
    # Test without bug image file
    mock_isfile.return_value = False
    args, has_overlay = build_overlay_args(1080)
    assert has_overlay is False
    assert len(args) == 0


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
def test_stream_file_success(mock_isfile: MagicMock, mock_exists: MagicMock, 
                              mock_load_playhead: MagicMock, mock_popen: MagicMock, 
                              temp_dir: Path):
    """Test successful file streaming."""
    mock_exists.return_value = True
    mock_isfile.return_value = True
    
    # Mock playhead state (no skip)
    mock_load_playhead.return_value = {
        "current_path": "/path/to/video.mp4",
        "current_index": 0,
    }
    
    # Mock FFmpeg process
    mock_process = MagicMock()
    mock_process.poll.return_value = 0  # Process finished
    mock_process.returncode = 0  # Success
    mock_process.stderr = None
    mock_popen.return_value = mock_process
    
    # Mock probe_video_height
    with patch("server.stream.probe_video_height", return_value=1080):
        with patch("server.stream.build_overlay_args", return_value=([], False)):
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
def test_stream_file_ffmpeg_failure(mock_isfile: MagicMock, mock_exists: MagicMock,
                                     mock_load_playhead: MagicMock, mock_popen: MagicMock):
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
    
    with patch("server.stream.probe_video_height", return_value=1080):
        with patch("server.stream.build_overlay_args", return_value=([], False)):
            result = stream_file("/path/to/video.mp4", 0, 1234567890.0)
            assert result is False

