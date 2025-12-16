#!/bin/bash
# Check and fix UI access issues

echo "========================================="
echo "UI Access Diagnostic & Fix"
echo "========================================="
echo ""

cd /mnt/blackhole/apps/channel

# Check dist folder contents
echo "1. Checking dist folder contents..."
docker exec tvchannel find /app/ui/channel-admin/dist -type f
echo ""

# Check if JS/CSS files exist
echo "2. Checking for JavaScript and CSS files..."
docker exec tvchannel ls -lh /app/ui/channel-admin/dist/assets/ 2>&1
echo ""

# Check index.html content
echo "3. Checking index.html content (first 30 lines)..."
docker exec tvchannel head -30 /app/ui/channel-admin/dist/index.html
echo ""

# Check port mapping
echo "4. Checking container port mapping..."
docker port tvchannel
echo ""

# Test from inside container
echo "5. Testing HTTP response from inside container..."
docker exec tvchannel curl -s http://localhost:8080/ | head -30
echo ""

# Check nginx error logs
echo "6. Checking nginx error logs..."
docker exec tvchannel tail -20 /var/log/nginx/error.log 2>&1
echo ""

# Check if port is listening
echo "7. Checking if port 8080 is listening..."
docker exec tvchannel netstat -tuln | grep 8080
echo ""

# Test API endpoint
echo "8. Testing API endpoint..."
docker exec tvchannel curl -s http://localhost:8080/api/healthz | head -5
echo ""

echo "========================================="
echo "If assets folder is empty or missing JS/CSS files,"
echo "the build may have failed. Rebuild with:"
echo "  docker build --no-cache -t tvchannel:latest -f server/Dockerfile ."
echo ""
echo "If port mapping looks wrong, check docker run command includes:"
echo "  -p 8080:8080"

