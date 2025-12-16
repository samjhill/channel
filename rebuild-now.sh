#!/bin/bash
# Quick rebuild script for TrueNAS

set -euo pipefail

echo "========================================="
echo "Rebuilding TV Channel Container"
echo "========================================="
echo ""

# Check if we're in the right directory
if [ ! -f "server/Dockerfile" ]; then
    echo "Error: Please run this from the app directory (where server/Dockerfile exists)"
    exit 1
fi

echo "1. Stopping existing container..."
docker stop tvchannel 2>/dev/null || echo "  Container not running"
docker rm tvchannel 2>/dev/null || echo "  Container doesn't exist"

echo ""
echo "2. Rebuilding Docker image..."
docker build -t tvchannel:latest -f server/Dockerfile . || {
    echo "Error: Build failed!"
    exit 1
}

echo ""
echo "3. Starting container..."

# Try docker compose first
if docker compose version >/dev/null 2>&1; then
    echo "  Using: docker compose"
    docker compose -f docker-compose.truenas.yml up -d || {
        echo "  docker compose failed, trying docker run..."
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
    echo "  Using: docker run"
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
echo "4. Checking container status..."
sleep 2
docker ps | grep tvchannel || echo "  Container not found in ps output"

echo ""
echo "5. Viewing recent logs..."
echo "========================================="
docker logs --tail 20 tvchannel 2>&1 | tail -20

echo ""
echo "========================================="
echo "Rebuild complete!"
echo ""
echo "To view full logs: docker logs -f tvchannel"
echo "To test stream: curl http://localhost:8080/channel/stream.m3u8"

