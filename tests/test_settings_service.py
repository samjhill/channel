"""Tests for settings_service module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from server.api.settings_service import (
    default_channel_template,
    get_channel,
    list_channels,
    load_settings,
    migrate_legacy_settings,
    normalize_channel,
    normalize_settings,
    normalize_show,
    replace_channel,
    save_settings,
    slugify,
    validate_settings,
)


@pytest.mark.unit
def test_slugify():
    """Test slugify function."""
    assert slugify("Test Channel") == "test-channel"
    assert slugify("My Awesome Show!") == "my-awesome-show"
    assert slugify("123") == "123"
    assert slugify("") == "channel"  # fallback
    assert slugify("", fallback="test") == "test"


@pytest.mark.unit
def test_default_channel_template():
    """Test default channel template."""
    template = default_channel_template()
    assert template["id"] == "hbn-main"
    assert template["name"] == "Hillside Broadcasting Network"
    assert template["enabled"] is True
    assert template["playback_mode"] == "sequential"
    assert "shows" in template
    assert "bumpers" in template
    assert "branding" in template


@pytest.mark.unit
def test_normalize_show():
    """Test show normalization."""
    show = {
        "label": "Test Show",
        "path": "Test Show",
        "include": True,
    }
    normalized = normalize_show(show)
    assert normalized["id"] == "test-show"
    assert normalized["label"] == "Test Show"
    assert normalized["include"] is True
    assert normalized["playback_mode"] == "inherit"
    assert normalized["weight"] == 1.0


@pytest.mark.unit
def test_normalize_show_with_weight():
    """Test show normalization with custom weight."""
    show = {
        "label": "Test Show",
        "weight": 2.5,
    }
    normalized = normalize_show(show)
    assert normalized["weight"] == 2.5


@pytest.mark.unit
def test_normalize_show_weight_limits():
    """Test show weight clamping."""
    show_min = {"label": "Show", "weight": -1.0}
    normalized_min = normalize_show(show_min)
    assert normalized_min["weight"] == 0.1  # Minimum
    
    show_max = {"label": "Show", "weight": 10.0}
    normalized_max = normalize_show(show_max)
    assert normalized_max["weight"] == 5.0  # Maximum


@pytest.mark.unit
def test_normalize_channel():
    """Test channel normalization."""
    channel = {
        "name": "My Channel",
        "media_root": "/media/tv",
        "playback_mode": "random",
    }
    normalized = normalize_channel(channel)
    assert normalized["id"] == "my-channel"
    assert normalized["name"] == "My Channel"
    assert normalized["media_root"] == "/media/tv"
    assert normalized["playback_mode"] == "random"
    assert normalized["enabled"] is True
    assert "shows" in normalized


@pytest.mark.unit
def test_normalize_channel_invalid_playback_mode():
    """Test channel normalization with invalid playback mode."""
    channel = {
        "name": "My Channel",
        "playback_mode": "invalid",
    }
    normalized = normalize_channel(channel)
    assert normalized["playback_mode"] == "sequential"  # Default


@pytest.mark.unit
def test_migrate_legacy_settings():
    """Test migrating legacy settings format."""
    legacy = {
        "include_shows": ["Show 1", "Show 2"],
    }
    migrated = migrate_legacy_settings(legacy)
    assert "channels" in migrated
    assert len(migrated["channels"]) == 1
    channel = migrated["channels"][0]
    assert len(channel["shows"]) == 2
    assert channel["shows"][0]["label"] == "Show 1"


@pytest.mark.unit
def test_normalize_settings():
    """Test settings normalization."""
    settings = {
        "channels": [
            {
                "name": "Channel 1",
                "shows": [{"label": "Show 1"}],
            }
        ]
    }
    normalized = normalize_settings(settings)
    assert "channels" in normalized
    assert len(normalized["channels"]) == 1
    assert normalized["channels"][0]["id"] == "channel-1"


@pytest.mark.unit
def test_normalize_settings_empty():
    """Test normalizing empty settings."""
    normalized = normalize_settings({})
    assert "channels" in normalized
    assert len(normalized["channels"]) == 1
    assert normalized["channels"][0]["id"] == "hbn-main"


@pytest.mark.unit
def test_validate_settings():
    """Test settings validation."""
    valid_settings = {"channels": [{"id": "test", "name": "Test"}]}
    validate_settings(valid_settings)  # Should not raise
    
    invalid_settings = {}
    with pytest.raises(ValueError, match="channels"):
        validate_settings(invalid_settings)
    
    empty_channels = {"channels": []}
    with pytest.raises(ValueError, match="At least one channel"):
        validate_settings(empty_channels)


@pytest.mark.unit
def test_load_and_save_settings(temp_dir: Path, monkeypatch):
    """Test loading and saving settings."""
    config_file = temp_dir / "channel_settings.json"
    monkeypatch.setenv("CHANNEL_CONFIG", str(config_file))
    
    import server.api.settings_service as ss_module
    ss_module._settings_cache = None
    ss_module._config_path_cache = None
    
    # Save settings
    settings = {
        "channels": [
            {
                "id": "test-channel",
                "name": "Test Channel",
                "enabled": True,
                "media_root": "/media/tv",
                "playback_mode": "sequential",
                "loop_entire_library": True,
                "shows": [],
            }
        ]
    }
    save_settings(settings)
    
    # Load settings
    loaded = load_settings()
    assert loaded["channels"][0]["id"] == "test-channel"
    assert loaded["channels"][0]["name"] == "Test Channel"


@pytest.mark.unit
def test_list_channels(temp_dir: Path, monkeypatch):
    """Test listing channels."""
    config_file = temp_dir / "channel_settings.json"
    settings = {
        "channels": [
            {"id": "channel-1", "name": "Channel 1"},
            {"id": "channel-2", "name": "Channel 2"},
        ]
    }
    config_file.write_text(json.dumps(settings, indent=2))
    monkeypatch.setenv("CHANNEL_CONFIG", str(config_file))
    
    import server.api.settings_service as ss_module
    ss_module._settings_cache = None
    ss_module._config_path_cache = None
    
    channels = list_channels()
    assert len(channels) == 2
    assert channels[0]["id"] == "channel-1"
    assert channels[1]["id"] == "channel-2"


@pytest.mark.unit
def test_get_channel(temp_dir: Path, monkeypatch):
    """Test getting a specific channel."""
    config_file = temp_dir / "channel_settings.json"
    settings = {
        "channels": [
            {"id": "channel-1", "name": "Channel 1"},
            {"id": "channel-2", "name": "Channel 2"},
        ]
    }
    config_file.write_text(json.dumps(settings, indent=2))
    monkeypatch.setenv("CHANNEL_CONFIG", str(config_file))
    
    import server.api.settings_service as ss_module
    ss_module._settings_cache = None
    ss_module._config_path_cache = None
    
    channel = get_channel("channel-1")
    assert channel is not None
    assert channel["id"] == "channel-1"
    assert channel["name"] == "Channel 1"
    
    assert get_channel("nonexistent") is None


@pytest.mark.unit
def test_replace_channel(temp_dir: Path, monkeypatch):
    """Test replacing a channel."""
    config_file = temp_dir / "channel_settings.json"
    settings = {
        "channels": [
            {"id": "channel-1", "name": "Channel 1"},
        ]
    }
    config_file.write_text(json.dumps(settings, indent=2))
    monkeypatch.setenv("CHANNEL_CONFIG", str(config_file))
    
    import server.api.settings_service as ss_module
    ss_module._settings_cache = None
    ss_module._config_path_cache = None
    
    updated = {
        "id": "channel-1",
        "name": "Updated Channel",
        "enabled": True,
        "media_root": "/media/tv",
        "playback_mode": "sequential",
        "loop_entire_library": True,
        "shows": [],
    }
    result = replace_channel("channel-1", updated)
    assert result["name"] == "Updated Channel"
    
    # Verify it was saved
    loaded = load_settings()
    assert loaded["channels"][0]["name"] == "Updated Channel"
    
    # Test replacing non-existent channel
    with pytest.raises(KeyError):
        replace_channel("nonexistent", updated)

