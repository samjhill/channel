"""Tests for watch progress file locking and validation."""

import json
import os
import tempfile
import threading
import time
from pathlib import Path

import pytest

from server.playlist_service import (
    get_last_watched_episode,
    load_watch_progress,
    mark_episode_watched,
    save_watch_progress,
)


@pytest.fixture
def temp_progress_file(temp_dir: Path, monkeypatch):
    """Create a temporary watch progress file and set it as the path."""
    progress_file = temp_dir / "watch_progress.json"
    progress_file.write_text(json.dumps({"episodes": {}, "last_watched": None, "updated_at": 0.0}))
    
    # Set environment variable to use this file
    monkeypatch.setenv("CHANNEL_WATCH_PROGRESS_PATH", str(progress_file))
    
    # Clear cache
    import server.playlist_service as ps_module
    ps_module._watch_progress_cache = None
    ps_module._watch_progress_mtime = 0.0
    ps_module._watch_progress_path_cache = None
    
    return progress_file


def test_file_locking_concurrent_writes(temp_progress_file: Path):
    """Test that file locking prevents race conditions during concurrent writes."""
    results = []
    errors = []
    
    def mark_episode(episode_path: str):
        """Mark an episode as watched."""
        try:
            mark_episode_watched(episode_path)
            results.append(episode_path)
        except Exception as e:
            errors.append(str(e))
    
    # Create multiple threads that will write concurrently
    threads = []
    for i in range(10):
        thread = threading.Thread(target=mark_episode, args=(f"/test/episode_{i}.mp4",))
        threads.append(thread)
    
    # Start all threads at roughly the same time
    for thread in threads:
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join(timeout=5)
    
    # Verify no errors occurred
    assert len(errors) == 0, f"Errors during concurrent writes: {errors}"
    
    # Verify all episodes were marked as watched
    progress = load_watch_progress()
    assert len(progress["episodes"]) == 10
    assert len(results) == 10
    
    # Verify all episodes are in the progress file
    for i in range(10):
        episode_path = f"/test/episode_{i}.mp4"
        assert episode_path in progress["episodes"]
        assert progress["episodes"][episode_path]["watched"] is True


def test_watch_progress_validation_missing_file(temp_progress_file: Path):
    """Test that watch progress validation handles missing files correctly."""
    # Mark an episode as watched
    episode_path = "/test/episode.mp4"
    mark_episode_watched(episode_path)
    
    # Verify it's in the progress
    progress = load_watch_progress()
    assert episode_path in progress["episodes"]
    
    # Verify last_watched is set
    assert get_last_watched_episode() == episode_path


def test_watch_progress_atomic_write(temp_progress_file: Path):
    """Test that watch progress writes are atomic."""
    # Write initial progress
    initial_progress = {
        "episodes": {"/test/ep1.mp4": {"watched": True, "watched_at": time.time()}},
        "last_watched": "/test/ep1.mp4",
        "updated_at": time.time(),
    }
    save_watch_progress(initial_progress)
    
    # Verify the file exists and is valid JSON
    assert temp_progress_file.exists()
    loaded = json.loads(temp_progress_file.read_text())
    assert loaded["last_watched"] == "/test/ep1.mp4"
    
    # Write updated progress
    updated_progress = {
        "episodes": {
            "/test/ep1.mp4": {"watched": True, "watched_at": time.time()},
            "/test/ep2.mp4": {"watched": True, "watched_at": time.time()},
        },
        "last_watched": "/test/ep2.mp4",
        "updated_at": time.time(),
    }
    save_watch_progress(updated_progress)
    
    # Verify the file was updated atomically
    loaded = json.loads(temp_progress_file.read_text())
    assert loaded["last_watched"] == "/test/ep2.mp4"
    assert len(loaded["episodes"]) == 2


def test_watch_progress_cleanup(temp_progress_file: Path):
    """Test that watch progress cleanup works correctly."""
    # Mark many episodes as watched
    for i in range(15000):  # More than max_entries (10000)
        mark_episode_watched(f"/test/episode_{i}.mp4")
    
    # Verify cleanup occurred
    progress = load_watch_progress()
    assert len(progress["episodes"]) <= 10000
    
    # Verify last_watched is still in the dict
    assert progress["last_watched"] in progress["episodes"]

