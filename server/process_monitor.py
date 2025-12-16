#!/usr/bin/env python3
"""
Process monitor for TV Channel streaming services.

Monitors generate_playlist.py and stream.py processes, automatically restarting
them if they crash. Uses exponential backoff to prevent restart loops.
"""

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
LOGGER = logging.getLogger(__name__)

# Process configurations
# Detect if running in Docker or baremetal
if Path("/app").exists():
    # Docker paths
    GENERATE_PLAYLIST_CMD = ["python3", "/app/server/generate_playlist.py"]
    STREAM_CMD = ["python3", "/app/server/stream.py"]
    API_CMD = ["python3", "-m", "uvicorn", "server.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
    TEST_CLIENT_CMD = ["python3", "-m", "http.server", "8081", "--directory", "/app/client/web_test"]
else:
    # Baremetal paths
    repo_root = Path(__file__).resolve().parent.parent
    GENERATE_PLAYLIST_CMD = ["python3", str(repo_root / "server" / "generate_playlist.py")]
    STREAM_CMD = ["python3", str(repo_root / "server" / "stream.py")]
    API_CMD = ["python3", "-m", "uvicorn", "server.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
    TEST_CLIENT_CMD = ["python3", "-m", "http.server", "8081", "--directory", str(repo_root / "client" / "web_test")]

PROCESSES = {
    "api": {
        "command": API_CMD,
        "restart_delay": 5,  # Initial delay in seconds
        "max_restart_delay": 300,  # Maximum delay (5 minutes)
        "restart_count": 0,
        "last_restart": 0,
        "process": None,
    },
    "generate_playlist": {
        "command": GENERATE_PLAYLIST_CMD,
        "restart_delay": 5,  # Initial delay in seconds
        "max_restart_delay": 300,  # Maximum delay (5 minutes)
        "restart_count": 0,
        "last_restart": 0,
        "process": None,
    },
    "stream": {
        "command": STREAM_CMD,
        "restart_delay": 5,
        "max_restart_delay": 300,
        "restart_count": 0,
        "last_restart": 0,
        "process": None,
    },
    "test_client": {
        "command": TEST_CLIENT_CMD,
        "restart_delay": 5,
        "max_restart_delay": 300,
        "restart_count": 0,
        "last_restart": 0,
        "process": None,
    },
}

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    LOGGER.info("Received signal %d, shutting down...", signum)
    shutdown_requested = True


def read_process_output(process: subprocess.Popen, name: str) -> None:
    """Read stdout/stderr from a process in a background thread to prevent blocking."""
    if not process.stdout:
        return
    
    try:
        # Read line by line to prevent blocking
        for line in iter(process.stdout.readline, ''):
            if not line:
                break
            # Log progress messages at INFO level, others at DEBUG
            line = line.rstrip()
            if line.startswith('[Progress]') or line.startswith('[Bumpers]') or line.startswith('[Playlist]'):
                LOGGER.info("%s: %s", name, line)
            else:
                LOGGER.debug("%s: %s", name, line)
    except Exception as e:
        LOGGER.debug("Error reading output from %s: %s", name, e)
    finally:
        if process.stdout:
            try:
                process.stdout.close()
            except Exception:
                pass


def start_process(name: str, config: Dict) -> Optional[subprocess.Popen]:
    """Start a process and return the Popen object."""
    try:
        LOGGER.info("Starting %s: %s", name, " ".join(config["command"]))
        process = subprocess.Popen(
            config["command"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        config["process"] = process
        config["last_restart"] = time.time()
        LOGGER.info("%s started with PID %d", name, process.pid)
        
        # Start a background thread to read stdout/stderr to prevent blocking
        output_thread = threading.Thread(
            target=read_process_output,
            args=(process, name),
            daemon=True,
            name=f"{name}-output-reader"
        )
        output_thread.start()
        
        return process
    except Exception as e:
        LOGGER.error("Failed to start %s: %s", name, e)
        return None


def calculate_backoff_delay(restart_count: int, base_delay: int, max_delay: int) -> int:
    """Calculate exponential backoff delay."""
    delay = min(base_delay * (2 ** restart_count), max_delay)
    return int(delay)


def monitor_process(name: str, config: Dict) -> None:
    """Monitor a single process and restart it if it crashes."""
    process = config["process"]
    
    if process is None:
        return
    
    # Check if process is still running
    if process.poll() is not None:
        # Process has terminated
        returncode = process.returncode
        LOGGER.warning(
            "%s process (PID %d) exited with code %d",
            name,
            process.pid,
            returncode,
        )
        
        # Output is already being read by background thread, no need to read here
        # Just wait a moment for the thread to finish reading any remaining output
        time.sleep(0.5)
        
        # Calculate backoff delay
        config["restart_count"] += 1
        delay = calculate_backoff_delay(
            config["restart_count"],
            config["restart_delay"],
            config["max_restart_delay"],
        )
        
        LOGGER.info(
            "Restarting %s in %d seconds (restart attempt #%d)",
            name,
            delay,
            config["restart_count"],
        )
        
        # Wait with backoff, but check for shutdown signal
        elapsed = 0
        while elapsed < delay and not shutdown_requested:
            time.sleep(1)
            elapsed += 1
        
        if not shutdown_requested:
            # Reset process reference and restart
            config["process"] = None
            start_process(name, config)
        else:
            LOGGER.info("Shutdown requested, not restarting %s", name)


def main():
    """Main monitoring loop."""
    global shutdown_requested
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    LOGGER.info("Starting process monitor...")
    
    # Ensure up-next bumper backgrounds are generated before starting processes
    try:
        LOGGER.info("Checking for up-next bumper backgrounds...")
        bg_script = Path("/app/scripts/bumpers/generate_up_next_backgrounds.py")
        if bg_script.exists():
            result = subprocess.run(
                [sys.executable, str(bg_script)],
                capture_output=True,
                timeout=600,  # 10 minute timeout
                cwd="/app"
            )
            if result.returncode == 0:
                LOGGER.info("Up-next bumper backgrounds ready")
            else:
                LOGGER.warning("Background generation had issues (may already exist): %s", result.stderr.decode()[:200] if result.stderr else "unknown")
        else:
            LOGGER.warning("Background generation script not found at %s", bg_script)
    except Exception as e:
        LOGGER.warning("Failed to check/generate backgrounds: %s (continuing anyway)", e)
    
    # Start all processes
    for name, config in PROCESSES.items():
        start_process(name, config)
    
    # Monitor loop
    LOGGER.info("Process monitor running. Monitoring %d processes.", len(PROCESSES))
    
    try:
        while not shutdown_requested:
            # Check each process
            for name, config in PROCESSES.items():
                monitor_process(name, config)
            
            # Sleep briefly before next check
            time.sleep(2)
    
    except KeyboardInterrupt:
        LOGGER.info("Keyboard interrupt received, shutting down...")
        shutdown_requested = True
    
    # Cleanup: terminate all processes
    LOGGER.info("Terminating monitored processes...")
    for name, config in PROCESSES.items():
        process = config.get("process")
        if process and process.poll() is None:
            LOGGER.info("Terminating %s (PID %d)...", name, process.pid)
            try:
                process.terminate()
                # Wait up to 5 seconds for graceful shutdown
                try:
                    process.wait(timeout=5)
                    LOGGER.info("%s terminated gracefully", name)
                except subprocess.TimeoutExpired:
                    LOGGER.warning("%s did not terminate, killing...", name)
                    process.kill()
                    process.wait()
                    LOGGER.info("%s killed", name)
            except Exception as e:
                LOGGER.error("Error terminating %s: %s", name, e)
    
    LOGGER.info("Process monitor stopped.")


if __name__ == "__main__":
    main()

