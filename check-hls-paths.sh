#!/bin/bash
# Check HLS paths and segment locations

echo "=== HLS Path Diagnostics ==="
echo ""

if ! docker ps | grep -q tvchannel; then
    echo "Container is not running"
    exit 1
fi

echo "1. Checking where FFmpeg is writing segments..."
docker exec tvchannel ps aux | grep ffmpeg | grep -o "/app/hls/[^ ]*" | head -1

echo ""
echo "2. Checking /app/hls directory inside container..."
docker exec tvchannel ls -lah /app/hls/ 2>/dev/null | head -20

echo ""
echo "3. Checking if /app/hls is a mount point..."
docker exec tvchannel mount | grep hls

echo ""
echo "4. Checking HLS volume mount from host..."
docker inspect tvchannel 2>/dev/null | grep -A 3 "hls" | grep -E "Source|Destination" || echo "   No HLS volume mount found"

echo ""
echo "5. Checking host HLS directory..."
HLS_HOST=$(docker inspect tvchannel 2>/dev/null | grep -A 5 "hls" | grep "Source" | head -1 | cut -d'"' -f4)
if [ -n "$HLS_HOST" ]; then
    echo "   Host path: $HLS_HOST"
    if [ -d "$HLS_HOST" ]; then
        echo "   ✓ Directory exists"
        ls -lah "$HLS_HOST" | head -20
    else
        echo "   ✗ Directory does NOT exist!"
    fi
else
    echo "   Could not determine host path"
fi

echo ""
echo "6. Checking segment files by pattern..."
docker exec tvchannel find /app/hls -name "*.ts" -type f 2>/dev/null | head -10

echo ""
echo "7. Checking if segments are being deleted..."
docker exec tvchannel ls -lah /app/hls/*.ts 2>/dev/null | wc -l

echo ""
echo "8. Checking FFmpeg process working directory..."
docker exec tvchannel pwdx $(docker exec tvchannel pgrep -f "ffmpeg.*stream.m3u8" | head -1) 2>/dev/null

echo ""
echo "=== Done ==="

