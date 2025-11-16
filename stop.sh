#!/bin/bash
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
DOCKER_CONTAINER="tvchannel"
PID_FILE="$SCRIPT_DIR/.start_pids"

echo -e "${BLUE}Stopping TV Channel services...${NC}"
echo ""

# Stop background processes from PID file
if [ -f "$PID_FILE" ]; then
    echo -e "${BLUE}Stopping background processes...${NC}"
    while read -r pid; do
        if kill -0 "$pid" 2>/dev/null; then
            echo "  Stopping process $pid"
            kill "$pid" 2>/dev/null || true
        fi
    done < "$PID_FILE"
    rm -f "$PID_FILE"
    echo -e "${GREEN}Background processes stopped${NC}"
else
    echo -e "${YELLOW}No PID file found, checking for running processes...${NC}"
    
    # Try to find and kill processes by port
    for port in 8000 5174 8081; do
        pid=$(lsof -ti ":$port" 2>/dev/null || true)
        if [ -n "$pid" ]; then
            echo "  Stopping process on port $port (PID: $pid)"
            kill "$pid" 2>/dev/null || true
        fi
    done
fi

echo ""

# Stop Docker container
if command -v docker >/dev/null 2>&1; then
    if docker ps --format '{{.Names}}' | grep -q "^${DOCKER_CONTAINER}$"; then
        echo -e "${BLUE}Stopping Docker container...${NC}"
        docker stop "$DOCKER_CONTAINER"
        echo -e "${GREEN}Docker container stopped${NC}"
    else
        echo -e "${YELLOW}Docker container is not running${NC}"
    fi
else
    echo -e "${YELLOW}Docker not found, skipping container stop${NC}"
fi

echo ""
echo -e "${GREEN}All services stopped!${NC}"

