#!/bin/bash
# Check if assets are present in container

echo "=== Checking Assets in Container ==="
echo ""

if ! docker ps | grep -q tvchannel; then
    echo "Container is not running"
    exit 1
fi

echo "1. Checking if assets directory exists..."
docker exec tvchannel ls -la /app/assets/ 2>/dev/null | head -10

echo ""
echo "2. Checking for branding directory..."
docker exec tvchannel ls -la /app/assets/branding/ 2>/dev/null | head -10

echo ""
echo "3. Checking for logo file..."
if docker exec tvchannel test -f /app/assets/branding/hbn_logo_bug.png; then
    echo "   ✓ Logo file exists"
    docker exec tvchannel ls -lh /app/assets/branding/hbn_logo_bug.png
else
    echo "   ✗ Logo file NOT found!"
    echo ""
    echo "4. Checking what's in branding directory..."
    docker exec tvchannel ls -la /app/assets/branding/ 2>/dev/null
fi

echo ""
echo "5. Checking if assets volume is mounted..."
docker inspect tvchannel 2>/dev/null | grep -A 5 "assets" | grep -E "Source|Destination" || echo "   No assets volume mount found"

