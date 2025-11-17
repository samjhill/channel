"""Pytest configuration and shared fixtures."""

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Generator
from unittest.mock import MagicMock, patch

import pytest

# Set test environment variables before importing modules
os.environ["CHANNEL_CONFIG"] = str(
    Path(__file__).parent / "fixtures" / "test_channel_settings.json"
)
os.environ["CHANNEL_PLAYLIST_PATH"] = str(
    Path(__file__).parent / "fixtures" / "test_playlist.txt"
)
os.environ["CHANNEL_PLAYHEAD_PATH"] = str(
    Path(__file__).parent / "fixtures" / "test_playhead.json"
)
os.environ["CHANNEL_WATCH_PROGRESS_PATH"] = str(
    Path(__file__).parent / "fixtures" / "test_watch_progress.json"
)


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for test files."""
    return tmp_path


@pytest.fixture
def test_config_file(temp_dir: Path) -> Path:
    """Create a test channel settings file."""
    config_file = temp_dir / "channel_settings.json"
    config_data = {
        "channels": [
            {
                "id": "test-channel",
                "name": "Test Channel",
                "enabled": True,
                "media_root": str(temp_dir / "media"),
                "playback_mode": "sequential",
                "loop_entire_library": True,
                "shows": [
                    {
                        "id": "show-1",
                        "label": "Test Show",
                        "path": "Test Show",
                        "include": True,
                        "playback_mode": "inherit",
                        "weight": 1.0,
                    }
                ],
                "bumpers": {"enable_up_next": True, "enable_intermission": True},
                "branding": {"show_bug_overlay": True},
            }
        ]
    }
    config_file.write_text(json.dumps(config_data, indent=2))
    return config_file


@pytest.fixture
def test_playlist_file(temp_dir: Path) -> Path:
    """Create a test playlist file."""
    playlist_file = temp_dir / "playlist.txt"
    media_dir = temp_dir / "media" / "Test Show" / "Season 01"
    media_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy video files
    episodes = [
        media_dir / "Episode 01.mp4",
        media_dir / "Episode 02.mp4",
        media_dir / "Episode 03.mp4",
    ]
    for ep in episodes:
        ep.write_text("fake video content")

    playlist_content = "\n".join(str(ep) for ep in episodes)
    playlist_file.write_text(playlist_content)
    return playlist_file


@pytest.fixture
def test_playhead_file(temp_dir: Path) -> Path:
    """Create a test playhead file."""
    playhead_file = temp_dir / "playhead.json"
    playhead_data = {
        "current_path": str(
            temp_dir / "media" / "Test Show" / "Season 01" / "Episode 01.mp4"
        ),
        "current_index": 0,
        "playlist_mtime": 1234567890.0,
        "playlist_path": str(temp_dir / "playlist.txt"),
        "entry_type": "episode",
    }
    playhead_file.write_text(json.dumps(playhead_data, indent=2))
    return playhead_file


@pytest.fixture
def test_watch_progress_file(temp_dir: Path) -> Path:
    """Create a test watch progress file."""
    progress_file = temp_dir / "watch_progress.json"
    progress_data = {
        "episodes": {},
        "last_watched": None,
        "updated_at": 0.0,
    }
    progress_file.write_text(json.dumps(progress_data, indent=2))
    return progress_file


@pytest.fixture
def mock_ffmpeg():
    """Mock FFmpeg subprocess calls."""
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "height=1080"
        mock_run.return_value = mock_result
        yield mock_run


@pytest.fixture
def mock_docker():
    """Mock Docker commands."""
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b""
        mock_result.stderr = b""
        mock_run.return_value = mock_result
        yield mock_run


@pytest.fixture
def api_client():
    """Create a test client for the FastAPI app."""
    from fastapi.testclient import TestClient
    from server.api.app import app

    # Clear caches before each test
    import server.api.app as app_module

    app_module._segments_cache = None
    app_module._segments_playlist_mtime = 0.0

    # Clear playlist service caches
    import server.playlist_service as ps_module

    ps_module._playlist_cache = None
    ps_module._playlist_mtime = 0.0
    ps_module._playhead_cache = None
    ps_module._playhead_mtime = 0.0
    ps_module._watch_progress_cache = None
    ps_module._watch_progress_mtime = 0.0

    # Clear settings cache
    import server.api.settings_service as ss_module

    ss_module._settings_cache = None
    ss_module._settings_mtime = 0.0
    ss_module._channels_index = {}

    return TestClient(app)
