#!/bin/bash
# Force rebuild without cache to ensure latest code is used

set -euo pipefail

echo "========================================="
echo "Force Rebuild (No Cache) - TV Channel"
echo "========================================="
echo ""

cd /mnt/blackhole/apps/channel

# Verify we have the latest code
echo "1. Checking git status..."
git status
echo ""
read -p "Press Enter to continue with rebuild, or Ctrl+C to pull latest code first..."

# Stop and remove container
echo ""
echo "2. Stopping and removing container..."
docker stop tvchannel 2>/dev/null || true
docker rm tvchannel 2>/dev/null || true

# Remove old image to force fresh build
echo ""
echo "3. Removing old image..."
docker rmi tvchannel:latest 2>/dev/null || echo "  Image doesn't exist, will build fresh"

# Rebuild WITHOUT cache
echo ""
echo "4. Building fresh image (no cache)..."
docker build --no-cache -t tvchannel:latest -f server/Dockerfile . || {
    echo "Error: Build failed!"
    exit 1
}

# Start container
echo ""
echo "5. Starting container..."

if docker compose version >/dev/null 2>&1; then
    docker compose -f docker-compose.truenas.yml up -d || {
        echo "docker compose failed, using docker run..."
        docker run -d \
          --name tvchannel \
          -p 8080:8080 \
          -v /mnt/blackhole/media/tv:/media/tvchannel:ro \
          -v /mnt/blackhole/apps/tvchannel/assets:/app/assets \
          -v /mnt/blackhole/apps/tvchannel/config:/app/config \
          -v /mnt/blackhole/apps/tvchannel/hls:/app/hls \
          --restart unless-stopped \
          tvchannel:latest
    }
else
    docker run -d \
      --name tvchannel \
      -p 8080:8080 \
      -v /mnt/blackhole/media/tv:/media/tvchannel:ro \
      -v /mnt/blackhole/apps/tvchannel/assets:/app/assets \
      -v /mnt/blackhole/apps/tvchannel/config:/app/config \
      -v /mnt/blackhole/apps/tvchannel/hls:/app/hls \
      --restart unless-stopped \
      tvchannel:latest
fi

echo ""
echo "6. Waiting a few seconds for container to start..."
sleep 5

echo ""
echo "7. Checking logs for errors..."
echo "========================================="
docker logs tvchannel 2>&1 | head -30

echo ""
echo "========================================="
echo "Rebuild complete!"
echo ""
echo "If you see the syntax error, the code on TrueNAS may not be updated."
echo "Run: git pull"
echo "Then rebuild again."

