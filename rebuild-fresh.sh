#!/bin/bash
# Rebuild container without cache to ensure latest code

set -e

echo "=== Rebuilding Container Without Cache ==="
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
echo "1. Stopping container..."
$COMPOSE_CMD -f docker-compose.truenas.yml down 2>/dev/null || true

echo ""
echo "2. Removing old image (if exists)..."
docker rmi tvchannel:latest 2>/dev/null || echo "   Image not found, will build new one"

echo ""
echo "3. Ensuring assets are copied to host directory..."
ASSETS_HOST="/mnt/blackhole/apps/tvchannel/assets"
if [ -d "assets/branding" ]; then
    mkdir -p "${ASSETS_HOST}/branding" 2>/dev/null || true
    if [ ! -f "${ASSETS_HOST}/branding/hbn_logo_bug.png" ] && [ -f "assets/branding/hbn_logo_bug.png" ]; then
        cp "assets/branding/hbn_logo_bug.png" "${ASSETS_HOST}/branding/" && echo "   ✓ Copied logo file"
    fi
fi

echo ""
echo "4. Building new image WITHOUT cache..."
docker build --no-cache -t tvchannel:latest -f server/Dockerfile .

if [ $? -ne 0 ]; then
    echo "   ✗ Build failed!"
    exit 1
fi

echo "   ✓ Build successful"
echo ""

echo "4. Starting container..."
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
echo "View logs:"
echo "  docker logs -f tvchannel"
