"""Tests for playlist_service module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from server.playlist_service import (
    build_playlist_segments,
    describe_episode,
    entry_type,
    find_segment_index_for_entry,
    flatten_segments,
    get_last_watched_episode,
    is_episode_entry,
    is_episode_watched,
    is_network_bumper,
    is_sassy_card,
    is_up_next_bumper,
    load_playhead_state,
    load_playlist_entries,
    load_watch_progress,
    mark_episode_watched,
    resolve_playhead_path,
    resolve_playlist_path,
    resolve_watch_progress_path,
    save_playhead_state,
    save_watch_progress,
    write_playlist_entries,
)


@pytest.mark.unit
def test_resolve_playlist_path(monkeypatch, temp_dir: Path):
    """Test resolving playlist path."""
    test_path = temp_dir / "playlist.txt"
    monkeypatch.setenv("CHANNEL_PLAYLIST_PATH", str(test_path))

    # Clear cache
    import server.playlist_service as ps_module

    ps_module._playlist_path_cache = None

    result = resolve_playlist_path()
    assert result == test_path


@pytest.mark.unit
def test_resolve_playhead_path(monkeypatch, temp_dir: Path):
    """Test resolving playhead path."""
    test_path = temp_dir / "playhead.json"
    monkeypatch.setenv("CHANNEL_PLAYHEAD_PATH", str(test_path))

    import server.playlist_service as ps_module

    ps_module._playhead_path_cache = None

    result = resolve_playhead_path()
    assert result == test_path


@pytest.mark.unit
def test_entry_type():
    """Test entry type detection."""
    assert entry_type("/path/to/episode.mp4") == "episode"
    assert entry_type("/path/to/episode.mkv") == "episode"
    assert entry_type("/path/to/episode.mov") == "episode"
    assert entry_type("/bumpers/up_next/show.mp4") == "bumper"
    assert entry_type("/bumpers/sassy/card.mp4") == "sassy"
    assert entry_type("/bumpers/network/brand.mp4") == "network"
    assert entry_type("/path/to/other.txt") == "other"


@pytest.mark.unit
def test_is_episode_entry():
    """Test episode entry detection."""
    assert is_episode_entry("/path/to/episode.mp4") is True
    assert is_episode_entry("/bumpers/up_next/show.mp4") is False
    assert is_episode_entry("/path/to/other.txt") is False


@pytest.mark.unit
def test_is_up_next_bumper():
    """Test up next bumper detection."""
    assert is_up_next_bumper("/bumpers/up_next/show.mp4") is True
    assert is_up_next_bumper("/bumpers/up_next\\show.mp4") is True  # Windows path
    assert is_up_next_bumper("/path/to/episode.mp4") is False


@pytest.mark.unit
def test_is_sassy_card():
    """Test sassy card detection."""
    assert is_sassy_card("/bumpers/sassy/card.mp4") is True
    assert is_sassy_card("/path/to/episode.mp4") is False


@pytest.mark.unit
def test_is_network_bumper():
    """Test network bumper detection."""
    assert is_network_bumper("/bumpers/network/brand.mp4") is True
    assert is_network_bumper("/path/to/episode.mp4") is False


@pytest.mark.unit
def test_load_and_write_playlist_entries(temp_dir: Path, monkeypatch):
    """Test loading and writing playlist entries."""
    playlist_file = temp_dir / "playlist.txt"
    monkeypatch.setenv("CHANNEL_PLAYLIST_PATH", str(playlist_file))

    import server.playlist_service as ps_module

    ps_module._playlist_path_cache = None
    ps_module._playlist_cache = None

    # Write entries
    entries = [
        "/path/to/episode1.mp4",
        "/path/to/episode2.mp4",
        "/path/to/episode3.mp4",
    ]
    mtime = write_playlist_entries(entries)
    assert mtime > 0

    # Load entries
    loaded_entries, loaded_mtime = load_playlist_entries()
    assert loaded_entries == entries
    assert abs(loaded_mtime - mtime) < 0.1


@pytest.mark.unit
def test_load_playlist_entries_not_found(monkeypatch, temp_dir: Path):
    """Test loading playlist when file doesn't exist."""
    playlist_file = temp_dir / "nonexistent.txt"
    monkeypatch.setenv("CHANNEL_PLAYLIST_PATH", str(playlist_file))

    import server.playlist_service as ps_module

    ps_module._playlist_path_cache = None
    ps_module._playlist_cache = None

    with pytest.raises(FileNotFoundError):
        load_playlist_entries()


@pytest.mark.unit
def test_load_and_save_playhead_state(temp_dir: Path, monkeypatch):
    """Test loading and saving playhead state."""
    playhead_file = temp_dir / "playhead.json"
    monkeypatch.setenv("CHANNEL_PLAYHEAD_PATH", str(playhead_file))

    import server.playlist_service as ps_module

    ps_module._playhead_path_cache = None
    ps_module._playhead_cache = None

    # Save state
    state = {
        "current_path": "/path/to/episode.mp4",
        "current_index": 0,
        "playlist_mtime": 1234567890.0,
        "playlist_path": "/path/to/playlist.txt",
        "entry_type": "episode",
    }
    save_playhead_state(state)

    # Load state
    loaded_state = load_playhead_state()
    assert loaded_state["current_path"] == state["current_path"]
    assert loaded_state["current_index"] == state["current_index"]
    assert "updated_at" in loaded_state


@pytest.mark.unit
def test_load_playhead_state_not_found(monkeypatch, temp_dir: Path):
    """Test loading playhead when file doesn't exist."""
    playhead_file = temp_dir / "nonexistent.json"
    monkeypatch.setenv("CHANNEL_PLAYHEAD_PATH", str(playhead_file))

    import server.playlist_service as ps_module

    ps_module._playhead_path_cache = None
    ps_module._playhead_cache = None

    state = load_playhead_state()
    assert state == {}


@pytest.mark.unit
def test_build_playlist_segments():
    """Test building playlist segments."""
    entries = [
        "/bumpers/up_next/show1.mp4",
        "/path/to/episode1.mp4",
        "/bumpers/sassy/card.mp4",
        "/bumpers/up_next/show2.mp4",
        "/path/to/episode2.mp4",
    ]

    segments = build_playlist_segments(entries)
    assert len(segments) == 2
    assert segments[0]["episode_path"] == "/path/to/episode1.mp4"
    assert segments[0]["start"] == 0  # Includes up_next bumper
    assert segments[0]["end"] == 3  # Includes sassy card
    assert segments[1]["episode_path"] == "/path/to/episode2.mp4"


@pytest.mark.unit
def test_flatten_segments():
    """Test flattening segments back to entries."""
    segments = [
        {
            "episode_path": "/path/to/episode1.mp4",
            "entries": ["/bumpers/up_next/show1.mp4", "/path/to/episode1.mp4"],
        },
        {
            "episode_path": "/path/to/episode2.mp4",
            "entries": ["/path/to/episode2.mp4"],
        },
    ]

    flattened = flatten_segments(segments)
    assert len(flattened) == 3
    assert flattened[0] == "/bumpers/up_next/show1.mp4"
    assert flattened[1] == "/path/to/episode1.mp4"
    assert flattened[2] == "/path/to/episode2.mp4"


@pytest.mark.unit
def test_find_segment_index_for_entry():
    """Test finding segment index for an entry."""
    segments = [
        {"episode_path": "/path/to/episode1.mp4", "entries": ["/path/to/episode1.mp4"]},
        {"episode_path": "/path/to/episode2.mp4", "entries": ["/path/to/episode2.mp4"]},
    ]

    assert find_segment_index_for_entry(segments, "/path/to/episode1.mp4") == 0
    assert find_segment_index_for_entry(segments, "/path/to/episode2.mp4") == 1
    assert find_segment_index_for_entry(segments, "/path/to/nonexistent.mp4") == -1


@pytest.mark.unit
def test_describe_episode():
    """Test describing an episode."""
    episode_path = "/media/tvchannel/Show Name/Season 01/Episode 01.mp4"
    media_root = "/media/tvchannel"

    description = describe_episode(episode_path, media_root, 0)
    assert description["path"] == episode_path
    assert description["type"] == "episode"
    assert description["controllable"] is True
    assert description["position"] == 0
    assert "label" in description
    assert "detail" in description


@pytest.mark.unit
def test_watch_progress_operations(temp_dir: Path, monkeypatch):
    """Test watch progress operations."""
    progress_file = temp_dir / "watch_progress.json"
    monkeypatch.setenv("CHANNEL_WATCH_PROGRESS_PATH", str(progress_file))

    import server.playlist_service as ps_module

    ps_module._watch_progress_path_cache = None
    ps_module._watch_progress_cache = None

    # Mark episode as watched
    episode_path = "/path/to/episode.mp4"
    mark_episode_watched(episode_path)

    # Check if watched
    assert is_episode_watched(episode_path) is True

    # Get last watched
    last_watched = get_last_watched_episode()
    assert last_watched == episode_path

    # Load progress
    progress = load_watch_progress()
    assert episode_path in progress["episodes"]
    assert progress["episodes"][episode_path]["watched"] is True


@pytest.mark.unit
def test_watch_progress_not_watched():
    """Test checking unwatched episode."""
    assert is_episode_watched("/path/to/unwatched.mp4") is False


@pytest.mark.unit
def test_resolve_watch_progress_path(monkeypatch, temp_dir: Path):
    """Test resolving watch progress path."""
    test_path = temp_dir / "watch_progress.json"
    monkeypatch.setenv("CHANNEL_WATCH_PROGRESS_PATH", str(test_path))

    import server.playlist_service as ps_module

    ps_module._watch_progress_path_cache = None

    result = resolve_watch_progress_path()
    assert result == test_path
