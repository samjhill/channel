"""
Helpers for restarting or refreshing the media streaming pipeline after config changes.
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Tuple

LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GENERATE_SCRIPT = REPO_ROOT / "generate_playlist.py"
DEFAULT_CONTAINER_ENV = "CHANNEL_DOCKER_CONTAINER"
FALLBACK_CONTAINER_NAME = "tvchannel"


def _run_command(command: str, capture_output: bool = False) -> Tuple[bool, str]:
    """Run a command and return (success, output/error)."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=capture_output,
            text=True,
            timeout=30,
        )
        output = result.stdout if capture_output else ""
        return True, output
    except subprocess.CalledProcessError as exc:
        error_msg = exc.stderr if capture_output and exc.stderr else str(exc)
        LOGGER.error("Command failed (%s): %s", exc.returncode, error_msg)
        return False, error_msg
    except subprocess.TimeoutExpired:
        LOGGER.error("Command timed out: %s", command)
        return False, "Command timed out"
    except Exception as exc:
        LOGGER.error("Unexpected error running command: %s", exc)
        return False, str(exc)


def restart_media_server() -> bool:
    """
    Attempt to restart the media server pipeline.

    If the environment variable CHANNEL_RESTART_COMMAND is set, it is executed.
    Otherwise we try to restart the Docker container, and if that fails,
    regenerate the playlist inside the container.
    """
    restart_cmd = os.environ.get("CHANNEL_RESTART_COMMAND")
    if restart_cmd:
        LOGGER.info("Running CHANNEL_RESTART_COMMAND: %s", restart_cmd)
        success, _ = _run_command(restart_cmd)
        if success:
            LOGGER.info("Restart command executed successfully.")
            return True
        else:
            LOGGER.warning("Restart command failed, trying Docker restart...")

    docker_bin = shutil.which("docker")
    container_name = os.environ.get(DEFAULT_CONTAINER_ENV, FALLBACK_CONTAINER_NAME)
    
    if docker_bin and container_name:
        # Sync config file to container first (in case volume mount isn't syncing)
        config_path = REPO_ROOT / "server" / "config" / "channel_settings.json"
        if config_path.exists():
            sync_cmd = f"{docker_bin} cp {shlex.quote(str(config_path))} {shlex.quote(container_name)}:/app/config/channel_settings.json"
            LOGGER.info("Syncing config file to container...")
            sync_success, sync_output = _run_command(sync_cmd, capture_output=True)
            if sync_success:
                LOGGER.info("Config file synced to container successfully.")
            else:
                LOGGER.warning("Failed to sync config file to container: %s", sync_output)
        
        # First, try to restart the container
        docker_cmd = f"{docker_bin} restart {shlex.quote(container_name)}"
        LOGGER.info("Attempting to restart Docker container: %s", container_name)
        restart_success, restart_output = _run_command(docker_cmd, capture_output=True)
        
        # Always regenerate playlist after restart (or if restart failed)
        # This ensures the playlist reflects the latest config
        regenerate_cmd = f"{docker_bin} exec {shlex.quote(container_name)} python3 /app/generate_playlist.py"
        LOGGER.info("Regenerating playlist inside container...")
        regen_success, regen_output = _run_command(regenerate_cmd, capture_output=True)
        
        if regen_success:
            LOGGER.info("Playlist regenerated inside container successfully.")
            if restart_success:
                LOGGER.info("Docker container '%s' restarted and playlist regenerated.", container_name)
            else:
                LOGGER.warning("Docker restart failed, but playlist was regenerated: %s", restart_output)
            return True
        else:
            LOGGER.error("Failed to regenerate playlist inside container: %s", regen_output)
            if restart_success:
                LOGGER.warning("Container restarted but playlist regeneration failed.")
            return False

    # Last resort: try to regenerate playlist on host (if running outside Docker)
    LOGGER.warning("Docker not available, attempting to regenerate playlist on host...")
    try:
        result = subprocess.run(
            ["python3", str(DEFAULT_GENERATE_SCRIPT)],
            check=True,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        LOGGER.info("Playlist regenerated on host (restart command not configured).")
        return True
    except subprocess.TimeoutExpired:
        LOGGER.error("Playlist regeneration timed out.")
    except Exception as exc:
        LOGGER.error("Failed to regenerate playlist on host: %s", exc)
    
    return False


