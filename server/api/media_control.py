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

LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GENERATE_SCRIPT = REPO_ROOT / "generate_playlist.py"
DEFAULT_CONTAINER_ENV = "CHANNEL_DOCKER_CONTAINER"
FALLBACK_CONTAINER_NAME = "tvchannel"


def _run_command(command: str) -> bool:
    try:
        subprocess.run(command, shell=True, check=True)
        return True
    except subprocess.CalledProcessError as exc:
        LOGGER.error("Command failed (%s): %s", exc.returncode, exc)
        return False


def restart_media_server() -> bool:
    """
    Attempt to restart the media server pipeline.

    If the environment variable CHANNEL_RESTART_COMMAND is set, it is executed.
    Otherwise we fall back to regenerating the playlist so at least new shows
    are reflected on the next stream loop.
    """

    restart_cmd = os.environ.get("CHANNEL_RESTART_COMMAND")
    if restart_cmd:
        LOGGER.info("Running CHANNEL_RESTART_COMMAND: %s", restart_cmd)
        return _run_command(restart_cmd)

    docker_bin = shutil.which("docker")
    container_name = os.environ.get(DEFAULT_CONTAINER_ENV, FALLBACK_CONTAINER_NAME)
    if docker_bin and container_name:
        docker_cmd = f"{docker_bin} restart {shlex.quote(container_name)}"
        if _run_command(docker_cmd):
            LOGGER.info("Docker container '%s' restarted.", container_name)
            return True

    # Best-effort fallback: refresh the playlist to reflect latest config.
    try:
        subprocess.run(
            ["python3", str(DEFAULT_GENERATE_SCRIPT)],
            check=True,
            env=os.environ.copy(),
        )
        LOGGER.info("Playlist regenerated (restart command not configured).")
    except Exception as exc:  # pragma: no cover - best effort logging
        LOGGER.error("Failed to regenerate playlist: %s", exc)
    return False


