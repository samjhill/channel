#!/bin/bash
set -euo pipefail

# Start nginx first so the HLS endpoint is available immediately
service nginx start || true

# Ensure up-next bumper backgrounds are generated before starting
echo "Checking for up-next bumper backgrounds..."
python3 /app/scripts/bumpers/generate_up_next_backgrounds.py || {
    echo "Warning: Failed to generate backgrounds, continuing anyway..."
}

# Start process monitor which will manage generate_playlist.py and stream.py
# The monitor will automatically restart processes if they crash
python3 /app/process_monitor.py
