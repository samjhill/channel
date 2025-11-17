#!/bin/bash
set -euo pipefail

# Start nginx first so the HLS endpoint is available immediately
service nginx start || true

# Start process monitor which will manage generate_playlist.py and stream.py
# The monitor will automatically restart processes if they crash
python3 /app/process_monitor.py
