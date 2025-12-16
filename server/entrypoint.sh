#!/bin/bash
set -euo pipefail

# Cleanup function for graceful shutdown
cleanup() {
    echo "Shutting down gracefully..."
    # Kill any remaining FFmpeg processes
    pkill -9 ffmpeg 2>/dev/null || true
    exit 0
}

trap cleanup SIGTERM SIGINT

# Ensure assets directory has required files (if volume mount is empty)
# This is a fallback - assets should be copied during setup, but this ensures they exist
if [ -d "/app/assets/branding" ] && [ ! -f "/app/assets/branding/hbn_logo_bug.png" ]; then
    # Check if we have assets in the image that we can copy
    if [ -d "/app/assets" ] && [ -f "/app/assets/branding/hbn_logo_bug.png" ]; then
        echo "Copying logo file to assets directory..."
        mkdir -p /app/assets/branding
        cp /app/assets/branding/hbn_logo_bug.png /app/assets/branding/ 2>/dev/null || true
    fi
fi

# Start nginx first so the HLS endpoint is available immediately
# Ensure our custom config is used and default sites are disabled
rm -f /etc/nginx/sites-enabled/* 2>/dev/null || true
nginx -t && service nginx start || true

# Clean up old HLS segments on startup (in case of previous crash)
echo "Cleaning up old HLS segments..."
python3 -c "
import sys
sys.path.insert(0, '/app')
from server.stream import cleanup_old_hls_segments
cleanup_old_hls_segments(max_age_hours=2.0, max_segments=100)
" || {
    echo "Warning: Failed to cleanup HLS segments, continuing anyway..."
}

# Ensure up-next bumper backgrounds are generated before starting
echo "Checking for up-next bumper backgrounds..."
python3 /app/scripts/bumpers/generate_up_next_backgrounds.py || {
    echo "Warning: Failed to generate backgrounds, continuing anyway..."
}

# Start process monitor which will manage generate_playlist.py and stream.py
# The monitor will automatically restart processes if they crash
python3 /app/process_monitor.py
