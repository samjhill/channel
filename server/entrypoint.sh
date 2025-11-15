#!/bin/bash
set -euo pipefail

python3 /app/generate_playlist.py

service nginx start

python3 /app/stream.py

