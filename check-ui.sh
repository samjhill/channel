#!/bin/bash
# Diagnostic script to check why admin UI isn't loading

echo "========================================="
echo "Admin UI Diagnostic Check"
echo "========================================="
echo ""

# Check if container is running
if ! docker ps | grep -q tvchannel; then
    echo "❌ Container 'tvchannel' is not running"
    exit 1
fi

echo "✓ Container is running"
echo ""

# Check if dist folder exists
echo "Checking if admin UI dist folder exists..."
docker exec tvchannel ls -la /app/ui/channel-admin/dist 2>&1 | head -10
echo ""

# Check if index.html exists
echo "Checking for index.html..."
docker exec tvchannel ls -la /app/ui/channel-admin/dist/index.html 2>&1
echo ""

# Check nginx config
echo "Checking nginx configuration..."
docker exec tvchannel cat /etc/nginx/nginx.conf | grep -A 5 "location /"
echo ""

# Check nginx status
echo "Checking nginx status..."
docker exec tvchannel service nginx status 2>&1 | head -5
echo ""

# Test nginx response
echo "Testing nginx response..."
docker exec tvchannel curl -I http://localhost:8080/ 2>&1 | head -10
echo ""

# Check if API is running
echo "Checking if API is running..."
docker exec tvchannel curl -s http://localhost:8000/api/healthz 2>&1 | head -5
echo ""

# Check logs for errors
echo "Recent nginx errors (if any):"
docker exec tvchannel tail -20 /var/log/nginx/error.log 2>&1 | tail -10
echo ""

echo "========================================="
echo "If dist folder doesn't exist, rebuild with:"
echo "  docker build --no-cache -t tvchannel:latest -f server/Dockerfile ."

