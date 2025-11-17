"""Tests for media_control module."""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from server.api.media_control import _run_command, restart_media_server


@pytest.mark.unit
@patch("subprocess.run")
def test_run_command_success(mock_run: MagicMock):
    """Test successful command execution."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Success"
    mock_run.return_value = mock_result

    success, output = _run_command("echo test", capture_output=True)
    assert success is True
    assert output == "Success"
    mock_run.assert_called_once()


@pytest.mark.unit
@patch("subprocess.run")
def test_run_command_failure(mock_run: MagicMock):
    """Test failed command execution."""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "Error"
    mock_run.side_effect = subprocess.CalledProcessError(1, "cmd", stderr="Error")

    success, output = _run_command("false", capture_output=True)
    assert success is False
    assert "Error" in output or len(output) > 0


@pytest.mark.unit
@patch("subprocess.run")
def test_run_command_timeout(mock_run: MagicMock):
    """Test command timeout."""
    mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)

    success, output = _run_command("sleep 100", capture_output=True)
    assert success is False
    assert "timed out" in output.lower()


@pytest.mark.unit
@patch("subprocess.run")
@patch("shutil.which")
def test_restart_media_server_with_docker(
    mock_which: MagicMock, mock_run: MagicMock, monkeypatch
):
    """Test restarting media server with Docker."""
    mock_which.return_value = "/usr/bin/docker"
    monkeypatch.setenv("CHANNEL_DOCKER_CONTAINER", "test-container")
    monkeypatch.delenv("CHANNEL_RESTART_COMMAND", raising=False)

    # Mock successful Docker commands
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_run.return_value = mock_result

    # Mock config file exists
    with patch("pathlib.Path.exists", return_value=True):
        result = restart_media_server()
        assert result is True
        # Should have called docker restart and docker exec
        assert mock_run.call_count >= 2


@pytest.mark.unit
@patch("subprocess.run")
def test_restart_media_server_with_custom_command(mock_run: MagicMock, monkeypatch):
    """Test restarting with custom restart command."""
    monkeypatch.setenv("CHANNEL_RESTART_COMMAND", "custom-restart-command")

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_run.return_value = mock_result

    result = restart_media_server()
    assert result is True
    mock_run.assert_called_once()
    # Check that custom command was called
    call_args = str(mock_run.call_args)
    assert "custom-restart-command" in call_args


@pytest.mark.unit
@patch("subprocess.run")
@patch("shutil.which")
def test_restart_media_server_no_docker(
    mock_which: MagicMock, mock_run: MagicMock, monkeypatch
):
    """Test restarting when Docker is not available."""
    mock_which.return_value = None  # Docker not found
    monkeypatch.delenv("CHANNEL_RESTART_COMMAND", raising=False)
    monkeypatch.delenv("CHANNEL_DOCKER_CONTAINER", raising=False)

    # Mock generate_playlist.py execution
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_run.return_value = mock_result

    result = restart_media_server()
    # Should attempt to regenerate playlist on host
    assert result is True
    mock_run.assert_called()


@pytest.mark.unit
@patch("subprocess.run")
@patch("shutil.which")
def test_restart_media_server_docker_failure(
    mock_which: MagicMock, mock_run: MagicMock, monkeypatch
):
    """Test restarting when Docker commands fail."""
    mock_which.return_value = "/usr/bin/docker"
    monkeypatch.setenv("CHANNEL_DOCKER_CONTAINER", "test-container")
    monkeypatch.delenv("CHANNEL_RESTART_COMMAND", raising=False)

    # Mock failed Docker commands
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "Container not found"
    mock_run.return_value = mock_result

    with patch("pathlib.Path.exists", return_value=True):
        result = restart_media_server()
        # Should still try to regenerate playlist
        assert mock_run.call_count >= 1
