#!/bin/bash
# Fix media volume mount issue

echo "========================================="
echo "Fixing Media Volume Mount"
echo "========================================="
echo ""

# Check current mounts
echo "1. Current volume mounts:"
docker inspect tvchannel | grep -A 20 "Mounts" | grep -E "(Source|Destination)" | head -20
echo ""

# Check if host path exists
echo "2. Checking host path /mnt/blackhole/media/tv:"
ls -ld /mnt/blackhole/media/tv 2>&1
echo ""

# List contents of host path
echo "3. Contents of /mnt/blackhole/media/tv (first 10):"
ls -1 /mnt/blackhole/media/tv 2>&1 | head -10
echo ""

echo "========================================="
echo "To fix, restart container with media mount:"
echo ""
echo "docker stop tvchannel"
echo "docker rm tvchannel"
echo "docker run -d \\"
echo "  --name tvchannel \\"
echo "  --memory=16g \\"
echo "  --cpus=8.0 \\"
echo "  -p 8080:8080 \\"
echo "  -p 8000:8000 \\"
echo "  -v /mnt/blackhole/media/tv:/media/tvchannel:ro \\"
echo "  -v /mnt/blackhole/apps/tvchannel/assets:/app/assets \\"
echo "  -v /mnt/blackhole/apps/tvchannel/config:/app/config \\"
echo "  -v /mnt/blackhole/apps/tvchannel/hls:/app/hls \\"
echo "  --restart unless-stopped \\"
echo "  tvchannel:latest"
echo ""

