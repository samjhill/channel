#!/bin/bash
# Comprehensive UI debugging script

echo "========================================="
echo "Admin UI Debugging"
echo "========================================="
echo ""

# Check if container exists
if ! docker ps -a | grep -q tvchannel; then
    echo "❌ Container 'tvchannel' does not exist"
    exit 1
fi

# Check if running
if ! docker ps | grep -q tvchannel; then
    echo "⚠️  Container exists but is not running"
    echo "Start it with: docker start tvchannel"
    exit 1
fi

echo "✓ Container is running"
echo ""

# Check dist folder structure
echo "1. Dist folder structure:"
docker exec tvchannel find /app/ui/channel-admin/dist -type f -o -type d | head -20
echo ""

# Check assets folder
echo "2. Assets folder contents:"
docker exec tvchannel ls -lah /app/ui/channel-admin/dist/assets/ 2>&1
echo ""

# Check index.html size and content
echo "3. Index.html details:"
docker exec tvchannel ls -lh /app/ui/channel-admin/dist/index.html
echo ""
echo "First 50 lines of index.html:"
docker exec tvchannel head -50 /app/ui/channel-admin/dist/index.html
echo ""

# Check if JS files are referenced
echo "4. Checking for JavaScript references in index.html:"
docker exec tvchannel grep -o 'src="[^"]*"' /app/ui/channel-admin/dist/index.html
echo ""

# Test nginx from inside
echo "5. Testing nginx response (full HTML):"
docker exec tvchannel curl -s http://localhost:8080/ | head -50
echo ""

# Check nginx config
echo "6. Nginx config for / location:"
docker exec tvchannel grep -A 5 'location /' /etc/nginx/nginx.conf
echo ""

# Check nginx error log
echo "7. Recent nginx errors:"
docker exec tvchannel tail -30 /var/log/nginx/error.log 2>&1
echo ""

# Check nginx access log
echo "8. Recent nginx access:"
docker exec tvchannel tail -10 /var/log/nginx/access.log 2>&1
echo ""

# Check port mapping
echo "9. Port mapping:"
docker port tvchannel
echo ""

# Test from host
echo "10. Testing from host:"
curl -I http://192.168.2.39:8080/ 2>&1 | head -15
echo ""

# Check if API works
echo "11. Testing API endpoint:"
curl -s http://192.168.2.39:8080/api/healthz | head -3
echo ""

echo "========================================="
echo "If assets folder is empty, rebuild with:"
echo "  docker build --no-cache -t tvchannel:latest -f server/Dockerfile ."
echo ""
echo "If port 8080 is not accessible, check firewall settings"

