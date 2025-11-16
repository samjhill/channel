#!/bin/bash
set -euo pipefail

# Start nginx first so the HLS endpoint is available immediately
service nginx start || true

# Generate playlist in background (it will create the stream.m3u8 file when ready)
python3 /app/generate_playlist.py &

# Start streaming (will wait for playlist if needed)
# Run in background to keep the script alive and allow nginx to keep running
python3 /app/stream.py &

# Keep the script alive
wait
