#!/bin/bash
set -euo pipefail

# Start nginx first so the HLS endpoint is available immediately
service nginx start

# Generate playlist in background (it will create the stream.m3u8 file when ready)
python3 /app/generate_playlist.py &

# Start streaming (will wait for playlist if needed)
python3 /app/stream.py

