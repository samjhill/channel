#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT=8081
echo "Serving test client on http://localhost:${PORT}"
echo "Press Ctrl+C to stop."
python3 -m http.server "${PORT}"


