#!/bin/bash
# Fix nginx in running container

echo "=== Fixing Nginx in Running Container ==="
echo ""

if ! docker ps | grep -q tvchannel; then
    echo "Container is not running"
    exit 1
fi

echo "1. Disabling default nginx sites..."
docker exec tvchannel rm -f /etc/nginx/sites-enabled/* 2>/dev/null || true
docker exec tvchannel rm -f /etc/nginx/sites-available/default 2>/dev/null || true

echo ""
echo "2. Verifying our config is being used..."
docker exec tvchannel nginx -t

echo ""
echo "3. Restarting nginx..."
docker exec tvchannel service nginx stop 2>/dev/null || true
sleep 1
docker exec tvchannel service nginx start

echo ""
echo "4. Waiting for nginx to start..."
sleep 2

echo ""
echo "5. Testing response..."
docker exec tvchannel curl -s http://localhost:8080/ | head -10

echo ""
echo "=== Done ==="
echo "Try accessing http://192.168.2.39:8080/ again"
echo "If it still shows welcome page, you may need to rebuild the container"

