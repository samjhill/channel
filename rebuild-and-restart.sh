#!/bin/bash
# Rebuild and restart the container

set -e

echo "=== Rebuilding and Restarting TV Channel ==="
echo ""

# Detect Docker Compose command
if command -v docker &> /dev/null && docker compose version &> /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
    echo "Using Docker Compose V2 (docker compose)"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
    echo "Using Docker Compose V1 (docker-compose)"
else
    echo "Error: Neither 'docker compose' nor 'docker-compose' found!"
    exit 1
fi

echo ""
echo "1. Ensuring assets are copied to host directory..."
ASSETS_HOST="/mnt/blackhole/apps/tvchannel/assets"
if [ -d "assets/branding" ]; then
    mkdir -p "${ASSETS_HOST}/branding" 2>/dev/null || true
    if [ ! -f "${ASSETS_HOST}/branding/hbn_logo_bug.png" ] && [ -f "assets/branding/hbn_logo_bug.png" ]; then
        cp "assets/branding/hbn_logo_bug.png" "${ASSETS_HOST}/branding/" && echo "   ✓ Copied logo file"
    fi
fi

echo ""
echo "2. Building Docker image..."
docker build -t tvchannel:latest -f server/Dockerfile .

if [ $? -ne 0 ]; then
    echo "   ✗ Build failed!"
    exit 1
fi

echo "   ✓ Build successful"
echo ""

echo "2. Stopping existing container (if running)..."
$COMPOSE_CMD -f docker-compose.truenas.yml down 2>/dev/null || true
echo "   ✓ Stopped"
echo ""

echo "3. Starting container..."
$COMPOSE_CMD -f docker-compose.truenas.yml up -d

if [ $? -eq 0 ]; then
    echo "   ✓ Container started"
else
    echo "   ✗ Failed to start container"
    exit 1
fi

echo ""
echo "5. Waiting for container to initialize..."
sleep 5

echo ""
echo "6. Checking container status..."
if docker ps | grep -q tvchannel; then
    echo "   ✓ Container is running"
else
    echo "   ✗ Container is not running!"
    echo "   Check logs: docker logs tvchannel"
    exit 1
fi

echo ""
echo "=== Success! ==="
echo ""
echo "Container is running. Check status:"
echo "  docker ps | grep tvchannel"
echo ""
echo "View logs:"
echo "  docker logs -f tvchannel"
echo ""
echo "Access points:"
echo "  Admin UI: http://192.168.2.39:8080/"
echo "  API:      http://192.168.2.39:8000/api/healthz"
echo "  Stream:   http://192.168.2.39:8080/channel/stream.m3u8"

