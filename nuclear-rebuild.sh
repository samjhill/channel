#!/bin/bash
# Nuclear rebuild - removes everything and rebuilds from scratch

set -e

echo "=== Nuclear Rebuild - Complete Clean Slate ==="
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
git status

echo ""
echo "1a. Ensuring assets are copied to host directory..."
ASSETS_HOST="/mnt/blackhole/apps/tvchannel/assets"
if [ -d "assets/branding" ]; then
    mkdir -p "${ASSETS_HOST}/branding" 2>/dev/null || true
    if [ ! -f "${ASSETS_HOST}/branding/hbn_logo_bug.png" ] && [ -f "assets/branding/hbn_logo_bug.png" ]; then
        cp "assets/branding/hbn_logo_bug.png" "${ASSETS_HOST}/branding/" && echo "   ✓ Copied logo file"
    else
        echo "   ✓ Logo file already exists"
    fi
fi

echo ""
echo "2. Verifying syntax locally..."
python3 -m py_compile server/stream.py
if [ $? -eq 0 ]; then
    echo "   ✓ Syntax check passed"
else
    echo "   ✗ Syntax error!"
    exit 1
fi

echo ""
echo "3. Stopping and removing container..."
$COMPOSE_CMD -f docker-compose.truenas.yml down 2>/dev/null || true
docker rm -f tvchannel 2>/dev/null || true
sleep 2

echo ""
echo "4. Removing ALL images and build cache..."
docker rmi tvchannel:latest 2>/dev/null || true
docker image prune -af 2>/dev/null || true
docker builder prune -af 2>/dev/null || true

echo ""
echo "5. Verifying stream.py is correct before build..."
if grep -q "global _current_ffmpeg_process" server/stream.py | head -1 | grep -q "^[[:space:]]*global"; then
    echo "   ✓ Global declaration found at function start"
else
    echo "   ⚠️  Checking global declarations..."
    grep -n "global _current_ffmpeg_process" server/stream.py
fi

echo ""
echo "6. Building COMPLETELY FRESH (no cache, no layers)..."
echo "   This may take 5-10 minutes (especially npm build step)..."
echo "   Building with progress output..."
docker build --no-cache --pull --progress=plain -t tvchannel:latest -f server/Dockerfile . 2>&1 | tee /tmp/docker-build.log | grep -E "(Step|RUN|COPY|npm|Building|Successfully)" || {
    echo "   Build output saved to /tmp/docker-build.log"
    echo "   Last 50 lines:"
    tail -50 /tmp/docker-build.log
}

if [ $? -ne 0 ]; then
    echo "   ✗ Build failed!"
    exit 1
fi

echo "   ✓ Build successful"
echo ""

echo "7. Verifying code in new image..."
docker run --rm tvchannel:latest python3 -m py_compile /app/server/stream.py 2>&1
if [ $? -eq 0 ]; then
    echo "   ✓ Syntax check passed in container"
else
    echo "   ✗ Syntax error in container!"
    exit 1
fi

echo ""
echo "8. Starting container..."
$COMPOSE_CMD -f docker-compose.truenas.yml up -d

if [ $? -eq 0 ]; then
    echo "   ✓ Container started"
else
    echo "   ✗ Failed to start container"
    exit 1
fi

echo ""
echo "9. Waiting and checking logs..."
sleep 5

if docker logs tvchannel 2>&1 | grep -q "SyntaxError"; then
    echo "   ✗ SyntaxError still in logs!"
    docker logs tvchannel 2>&1 | grep -A 3 "SyntaxError"
    exit 1
else
    echo "   ✓ No syntax errors in logs"
fi

echo ""
echo "=== Success! ==="
echo "Container rebuilt from scratch with latest code."

