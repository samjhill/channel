#!/bin/bash
# Fix nginx to serve admin UI instead of default welcome page

echo "=== Fixing Nginx Configuration ==="
echo ""

if ! docker ps | grep -q tvchannel; then
    echo "Container is not running"
    exit 1
fi

echo "1. Checking for default nginx sites..."
docker exec tvchannel ls -la /etc/nginx/sites-enabled/ 2>/dev/null || echo "   No sites-enabled directory"

echo ""
echo "2. Checking nginx main config..."
docker exec tvchannel cat /etc/nginx/nginx.conf | head -20

echo ""
echo "3. Checking if our custom config is being used..."
docker exec tvchannel nginx -t 2>&1

echo ""
echo "4. Checking what nginx is actually serving on port 8080..."
docker exec tvchannel netstat -tlnp | grep 8080 || docker exec tvchannel ss -tlnp | grep 8080

echo ""
echo "5. Restarting nginx with our config..."
docker exec tvchannel nginx -s reload 2>&1 || docker exec tvchannel service nginx restart 2>&1

echo ""
echo "6. Testing again..."
sleep 2
docker exec tvchannel curl -s http://localhost:8080/ | head -10

echo ""
echo "=== If still showing welcome page ==="
echo "The issue might be that nginx default site is enabled."
echo "We need to ensure our custom nginx.conf is the only one being used."

