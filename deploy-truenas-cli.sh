#!/bin/bash
# Deploy TV Channel to TrueNAS Scale via command line
# This avoids the build context issue with TrueNAS Apps UI

set -euo pipefail

echo "========================================="
echo "TV Channel - TrueNAS Scale Deployment"
echo "========================================="
echo ""

# Configuration
POOL_NAME="${POOL_NAME:-blackhole}"
APP_NAME="${APP_NAME:-channel}"  # Can be 'channel' or 'tvchannel'
APP_DIR="/mnt/${POOL_NAME}/apps/${APP_NAME}"
COMPOSE_FILE="${APP_DIR}/docker-compose.truenas.yml"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

# Auto-detect current directory if running from app directory
if [ -f "docker-compose.truenas.yml" ] && [ -f "server/Dockerfile" ]; then
    echo -e "${BLUE}Detected app directory: $(pwd)${NC}"
    APP_DIR="$(pwd)"
    COMPOSE_FILE="${APP_DIR}/docker-compose.truenas.yml"
else
    # Check if app directory exists
    if [ ! -d "$APP_DIR" ]; then
        echo -e "${RED}Error: App directory not found: $APP_DIR${NC}"
        echo "Either:"
        echo "  1. Run this script from the app directory, or"
        echo "  2. Set APP_NAME: APP_NAME=channel $0"
        exit 1
    fi
    cd "$APP_DIR"
fi

# Check if docker-compose file exists
if [ ! -f "$COMPOSE_FILE" ]; then
    echo -e "${RED}Error: docker-compose file not found: $COMPOSE_FILE${NC}"
    echo "Please ensure docker-compose.truenas.yml is in the app directory"
    exit 1
fi

# Check if Dockerfile exists
if [ ! -f "server/Dockerfile" ]; then
    echo -e "${RED}Error: Dockerfile not found: server/Dockerfile${NC}"
    echo "Please ensure the server directory and Dockerfile are present"
    exit 1
fi

echo -e "${BLUE}Building Docker image...${NC}"
echo "Build context: $(pwd)"
docker build -t tvchannel:latest -f server/Dockerfile . || {
    echo -e "${RED}Error: Failed to build Docker image${NC}"
    echo "Make sure you're in the app directory with server/Dockerfile present"
    exit 1
}

echo -e "${GREEN}Image built successfully!${NC}"
echo ""

echo -e "${BLUE}Starting container with docker compose...${NC}"
# Try docker compose (V2) first, fall back to docker-compose (V1)
if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
elif docker-compose version >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
else
    echo -e "${RED}Error: Neither 'docker compose' nor 'docker-compose' found${NC}"
    exit 1
fi

$COMPOSE_CMD -f "$COMPOSE_FILE" down 2>/dev/null || true
$COMPOSE_CMD -f "$COMPOSE_FILE" up -d || {
    echo -e "${RED}Error: Failed to start container${NC}"
    exit 1
}

echo ""
echo -e "${GREEN}Deployment complete!${NC}"
echo ""
echo "Container status:"
$COMPOSE_CMD -f "$COMPOSE_FILE" ps

echo ""
echo "To view logs:"
echo "  $COMPOSE_CMD -f $COMPOSE_FILE logs -f"
echo ""
echo "To stop:"
echo "  $COMPOSE_CMD -f $COMPOSE_FILE down"
echo ""
echo "Stream URL:"
echo "  http://$(hostname -I | awk '{print $1}'):8080/channel/stream.m3u8"

