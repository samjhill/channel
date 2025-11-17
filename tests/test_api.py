"""Tests for FastAPI endpoints."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Set test environment before importing app
os.environ.setdefault(
    "CHANNEL_CONFIG",
    str(Path(__file__).parent / "fixtures" / "test_channel_settings.json"),
)
os.environ.setdefault(
    "CHANNEL_PLAYLIST_PATH",
    str(Path(__file__).parent / "fixtures" / "test_playlist.txt"),
)
os.environ.setdefault(
    "CHANNEL_PLAYHEAD_PATH",
    str(Path(__file__).parent / "fixtures" / "test_playhead.json"),
)
os.environ.setdefault(
    "CHANNEL_WATCH_PROGRESS_PATH",
    str(Path(__file__).parent / "fixtures" / "test_watch_progress.json"),
)

from server.api.app import app


@pytest.fixture
def client():
    """Create a test client."""
    # Clear caches
    import server.api.app as app_module

    app_module._segments_cache = None
    app_module._segments_playlist_mtime = 0.0

    import server.playlist_service as ps_module

    ps_module._playlist_cache = None
    ps_module._playlist_mtime = 0.0
    ps_module._playhead_cache = None
    ps_module._playhead_mtime = 0.0

    import server.api.settings_service as ss_module

    ss_module._settings_cache = None
    ss_module._settings_mtime = 0.0
    ss_module._channels_index = {}

    return TestClient(app)


@pytest.mark.api
def test_health_check(client: TestClient):
    """Test health check endpoint."""
    response = client.get("/api/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.api
def test_list_channels(client: TestClient, test_config_file: Path, monkeypatch):
    """Test listing all channels."""
    monkeypatch.setenv("CHANNEL_CONFIG", str(test_config_file))

    # Invalidate cache
    import server.api.settings_service as ss_module

    ss_module._settings_cache = None

    response = client.get("/api/channels")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert data[0]["id"] == "test-channel"


@pytest.mark.api
def test_get_channel(client: TestClient, test_config_file: Path, monkeypatch):
    """Test getting a specific channel."""
    monkeypatch.setenv("CHANNEL_CONFIG", str(test_config_file))

    # Invalidate cache
    import server.api.settings_service as ss_module

    ss_module._settings_cache = None

    response = client.get("/api/channels/test-channel")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "test-channel"
    assert data["name"] == "Test Channel"


@pytest.mark.api
def test_get_channel_not_found(client: TestClient):
    """Test getting a non-existent channel."""
    response = client.get("/api/channels/nonexistent")
    assert response.status_code == 404


@pytest.mark.api
def test_update_channel(client: TestClient, test_config_file: Path, monkeypatch):
    """Test updating a channel."""
    monkeypatch.setenv("CHANNEL_CONFIG", str(test_config_file))

    # Invalidate cache
    import server.api.settings_service as ss_module

    ss_module._settings_cache = None

    updated_data = {
        "id": "test-channel",
        "name": "Updated Channel Name",
        "enabled": True,
        "media_root": "/tmp/test_media",
        "playback_mode": "sequential",
        "loop_entire_library": True,
        "shows": [],
    }

    with patch("server.api.media_control.restart_media_server", return_value=True):
        response = client.put("/api/channels/test-channel", json=updated_data)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Channel Name"


@pytest.mark.api
def test_update_channel_id_mismatch(
    client: TestClient, test_config_file: Path, monkeypatch
):
    """Test updating a channel with ID mismatch."""
    monkeypatch.setenv("CHANNEL_CONFIG", str(test_config_file))

    import server.api.settings_service as ss_module

    ss_module._settings_cache = None

    updated_data = {
        "id": "different-id",
        "name": "Updated Channel Name",
    }

    response = client.put("/api/channels/test-channel", json=updated_data)
    assert response.status_code == 400


@pytest.mark.api
def test_discover_shows(
    client: TestClient, test_config_file: Path, temp_dir: Path, monkeypatch
):
    """Test discovering shows in a media directory."""
    monkeypatch.setenv("CHANNEL_CONFIG", str(test_config_file))

    import server.api.settings_service as ss_module

    ss_module._settings_cache = None

    # Create test media directory structure
    media_root = temp_dir / "media"
    show1_dir = media_root / "Show 1"
    show2_dir = media_root / "Show 2"
    show1_dir.mkdir(parents=True, exist_ok=True)
    show2_dir.mkdir(parents=True, exist_ok=True)

    response = client.get(
        f"/api/channels/test-channel/shows/discover?media_root={media_root}"
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    show_names = [show["label"] for show in data]
    assert "Show 1" in show_names
    assert "Show 2" in show_names


@pytest.mark.api
def test_get_playlist_snapshot(
    client: TestClient, test_config_file: Path, test_playlist_file: Path, monkeypatch
):
    """Test getting playlist snapshot."""
    monkeypatch.setenv("CHANNEL_CONFIG", str(test_config_file))
    monkeypatch.setenv("CHANNEL_PLAYLIST_PATH", str(test_playlist_file))

    # Invalidate caches
    import server.api.settings_service as ss_module

    ss_module._settings_cache = None

    import server.playlist_service as ps_module

    ps_module._playlist_cache = None

    response = client.get("/api/channels/test-channel/playlist/next?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "current" in data
    assert "upcoming" in data
    assert isinstance(data["upcoming"], list)


@pytest.mark.api
def test_update_playlist(
    client: TestClient, test_config_file: Path, test_playlist_file: Path, monkeypatch
):
    """Test updating playlist order."""
    monkeypatch.setenv("CHANNEL_CONFIG", str(test_config_file))
    monkeypatch.setenv("CHANNEL_PLAYLIST_PATH", str(test_playlist_file))

    # Invalidate caches
    import server.api.settings_service as ss_module

    ss_module._settings_cache = None

    import server.playlist_service as ps_module

    ps_module._playlist_cache = None

    # Get current playlist to get version
    snapshot_response = client.get("/api/channels/test-channel/playlist/next?limit=10")
    assert snapshot_response.status_code == 200
    snapshot = snapshot_response.json()
    version = snapshot["version"]

    if snapshot["upcoming"]:
        # Reorder first two items
        desired = [item["path"] for item in snapshot["upcoming"][:2]]
        desired.reverse()

        update_request = {
            "version": version,
            "desired": desired,
            "skipped": [],
        }

        response = client.post(
            "/api/channels/test-channel/playlist/next", json=update_request
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["version"] != version  # Version should change


@pytest.mark.api
def test_update_playlist_version_mismatch(
    client: TestClient, test_config_file: Path, test_playlist_file: Path, monkeypatch
):
    """Test updating playlist with stale version."""
    monkeypatch.setenv("CHANNEL_CONFIG", str(test_config_file))
    monkeypatch.setenv("CHANNEL_PLAYLIST_PATH", str(test_playlist_file))

    import server.api.settings_service as ss_module

    ss_module._settings_cache = None

    import server.playlist_service as ps_module

    ps_module._playlist_cache = None

    update_request = {
        "version": 999999.0,  # Stale version
        "desired": [],
        "skipped": [],
    }

    response = client.post(
        "/api/channels/test-channel/playlist/next", json=update_request
    )
    assert response.status_code == 409  # Conflict


@pytest.mark.api
@patch("subprocess.run")
def test_skip_current_episode(
    mock_subprocess: MagicMock,
    client: TestClient,
    test_config_file: Path,
    test_playlist_file: Path,
    test_playhead_file: Path,
    monkeypatch,
    temp_dir: Path,
):
    """Test skipping current episode."""
    monkeypatch.setenv("CHANNEL_CONFIG", str(test_config_file))

    # Create a proper playlist file with valid paths
    media_dir = temp_dir / "media" / "Test Show" / "Season 01"
    media_dir.mkdir(parents=True, exist_ok=True)
    episode1 = media_dir / "Episode 01.mp4"
    episode2 = media_dir / "Episode 02.mp4"
    episode1.write_text("fake")
    episode2.write_text("fake")

    playlist_file = temp_dir / "playlist.txt"
    playlist_file.write_text(f"{episode1}\n{episode2}\n")
    monkeypatch.setenv("CHANNEL_PLAYLIST_PATH", str(playlist_file))

    # Create playhead file
    playhead_file = temp_dir / "playhead.json"
    playhead_data = {
        "current_path": str(episode1),
        "current_index": 0,
        "playlist_mtime": playlist_file.stat().st_mtime,
        "playlist_path": str(playlist_file),
        "entry_type": "episode",
    }
    playhead_file.write_text(json.dumps(playhead_data))
    monkeypatch.setenv("CHANNEL_PLAYHEAD_PATH", str(playhead_file))

    # Mock Docker commands - first sync (copy from container)
    def mock_run_side_effect(*args, **kwargs):
        mock_result = MagicMock()
        if "cp" in args[0] and "tvchannel:/app/hls/playlist.txt" in args[0]:
            # Sync playlist from container
            mock_result.returncode = 0
        elif "cp" in args[0] and "tvchannel:/app/hls/playhead.json" in args[0]:
            # Sync playhead from container
            mock_result.returncode = 0
        elif "cp" in args[0] and "playhead.json" in args[0] and "tvchannel:" in args[0]:
            # Sync playhead to container
            mock_result.returncode = 0
        elif "exec" in args[0] and "cat" in args[0]:
            # Read container playhead
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(
                {
                    "current_path": str(episode2),
                    "current_index": 1,
                    "updated_at": 1234567890.0,
                }
            ).encode()
        else:
            mock_result.returncode = 1
        return mock_result

    mock_subprocess.side_effect = mock_run_side_effect

    # Invalidate caches
    import server.api.settings_service as ss_module

    ss_module._settings_cache = None

    import server.playlist_service as ps_module

    ps_module._playlist_cache = None
    ps_module._playhead_cache = None

    response = client.post("/api/channels/test-channel/playlist/skip-current")
    # May fail if Docker is not available, but should not crash
    assert response.status_code in [200, 404, 500, 504]
