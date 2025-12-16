#!/bin/bash
# Start TV Channel container with all settings

docker run -d \
  --name tvchannel \
  --memory=16g \
  --cpus=8.0 \
  -p 8080:8080 \
  -p 8000:8000 \
  -v /mnt/blackhole/media/tv:/media/tvchannel:ro \
  -v /mnt/blackhole/apps/tvchannel/assets:/app/assets \
  -v /mnt/blackhole/apps/tvchannel/config:/app/config \
  -v /mnt/blackhole/apps/tvchannel/hls:/app/hls \
  --restart unless-stopped \
  tvchannel:latest

echo ""
echo "Container started!"
echo ""
echo "Access points:"
echo "  Admin UI: http://192.168.2.39:8080/"
echo "  API:      http://192.168.2.39:8080/api/ or http://192.168.2.39:8000/"
echo "  Stream:   http://192.168.2.39:8080/channel/stream.m3u8"
echo ""
echo "Check status: docker ps | grep tvchannel"
echo "View logs:    docker logs -f tvchannel"

