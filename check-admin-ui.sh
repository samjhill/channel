#!/bin/bash
# Check if admin UI is built and accessible

echo "=== Checking Admin UI ==="
echo ""

if ! docker ps | grep -q tvchannel; then
    echo "Container is not running"
    exit 1
fi

echo "1. Checking if dist folder exists..."
if docker exec tvchannel test -d /app/ui/channel-admin/dist; then
    echo "   ✓ dist folder exists"
    
    echo ""
    echo "2. Checking dist folder contents..."
    docker exec tvchannel ls -la /app/ui/channel-admin/dist/ | head -20
    
    echo ""
    echo "3. Checking for index.html..."
    if docker exec tvchannel test -f /app/ui/channel-admin/dist/index.html; then
        echo "   ✓ index.html exists"
        docker exec tvchannel head -20 /app/ui/channel-admin/dist/index.html
    else
        echo "   ✗ index.html NOT found!"
    fi
    
    echo ""
    echo "4. Checking nginx config..."
    docker exec tvchannel cat /etc/nginx/nginx.conf | grep -A 5 "location /"
    
    echo ""
    echo "5. Testing nginx response..."
    docker exec tvchannel curl -s http://localhost:8080/ | head -20
    
else
    echo "   ✗ dist folder does NOT exist!"
    echo ""
    echo "   The admin UI was not built during Docker build."
    echo "   Check Docker build logs for npm build errors."
fi

echo ""
echo "6. Checking nginx error logs..."
docker exec tvchannel tail -20 /var/log/nginx/error.log 2>/dev/null || echo "   No error log found"

