#!/bin/bash
# Force rebuild ensuring latest code is used

set -e

echo "=== Force Rebuild with Latest Code ==="
echo ""

# Detect Docker Compose command
if command -v docker &> /dev/null && docker compose version &> /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    echo "Error: Docker Compose not found!"
    exit 1
fi

echo "1. Pulling latest code..."
git pull

if [ $? -ne 0 ]; then
    echo "   ✗ Git pull failed!"
    exit 1
fi

echo "   ✓ Code updated"
echo ""

echo "2. Ensuring assets are copied to host directory..."
ASSETS_HOST="/mnt/blackhole/apps/tvchannel/assets"
if [ -d "assets/branding" ]; then
    mkdir -p "${ASSETS_HOST}/branding" 2>/dev/null || true
    if [ ! -f "${ASSETS_HOST}/branding/hbn_logo_bug.png" ] && [ -f "assets/branding/hbn_logo_bug.png" ]; then
        cp "assets/branding/hbn_logo_bug.png" "${ASSETS_HOST}/branding/" && echo "   ✓ Copied logo file"
    fi
fi

echo ""
echo "3. Verifying syntax..."
python3 -m py_compile server/stream.py 2>&1
if [ $? -eq 0 ]; then
    echo "   ✓ Syntax check passed"
else
    echo "   ✗ Syntax error found!"
    exit 1
fi

echo ""
echo "4. Stopping and removing container..."
$COMPOSE_CMD -f docker-compose.truenas.yml down 2>/dev/null || true
docker rm -f tvchannel 2>/dev/null || true

echo ""
echo "5. Removing ALL images (including intermediate layers)..."
docker rmi tvchannel:latest 2>/dev/null || true
docker image prune -f

echo ""
echo "6. Building FRESH image (no cache)..."
docker build --no-cache --pull -t tvchannel:latest -f server/Dockerfile .

if [ $? -ne 0 ]; then
    echo "   ✗ Build failed!"
    exit 1
fi

echo "   ✓ Build successful"
echo ""

echo "6. Starting container..."
$COMPOSE_CMD -f docker-compose.truenas.yml up -d

if [ $? -eq 0 ]; then
    echo "   ✓ Container started"
else
    echo "   ✗ Failed to start container"
    exit 1
fi

echo ""
echo "8. Waiting for initialization..."
sleep 5

echo ""
echo "9. Checking logs for errors..."
if docker logs tvchannel 2>&1 | grep -q "SyntaxError"; then
    echo "   ✗ SyntaxError still present in logs!"
    echo "   Full error:"
    docker logs tvchannel 2>&1 | grep -A 5 "SyntaxError"
    exit 1
else
    echo "   ✓ No syntax errors in logs"
fi

echo ""
echo "=== Success! ==="
echo ""
echo "Container rebuilt with latest code."
echo "View logs: docker logs -f tvchannel"

