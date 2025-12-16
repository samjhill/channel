#!/bin/bash
# Diagnose streaming issues

echo "=== Stream Diagnostics ==="
echo ""

if ! docker ps | grep -q tvchannel; then
    echo "Container is not running"
    exit 1
fi

echo "1. Checking if stream.py process is running..."
if docker exec tvchannel pgrep -f "stream.py" >/dev/null 2>&1; then
    echo "   ✓ stream.py is running"
    docker exec tvchannel ps aux | grep stream.py | grep -v grep
else
    echo "   ✗ stream.py is NOT running!"
fi

echo ""
echo "2. Checking if FFmpeg processes are running..."
FFMPEG_COUNT=$(docker exec tvchannel pgrep -f ffmpeg | wc -l)
if [ "$FFMPEG_COUNT" -gt 0 ]; then
    echo "   ✓ Found $FFMPEG_COUNT FFmpeg process(es)"
    docker exec tvchannel ps aux | grep ffmpeg | grep -v grep | head -3
else
    echo "   ✗ No FFmpeg processes running!"
fi

echo ""
echo "3. Checking HLS playlist file..."
if docker exec tvchannel test -f /app/hls/stream.m3u8; then
    echo "   ✓ Playlist file exists"
    echo "   Contents:"
    docker exec tvchannel head -20 /app/hls/stream.m3u8
    echo ""
    SEGMENT_COUNT=$(docker exec tvchannel grep -c "^stream" /app/hls/stream.m3u8 2>/dev/null || echo "0")
    echo "   Segment count: $SEGMENT_COUNT"
else
    echo "   ✗ Playlist file does NOT exist!"
fi

echo ""
echo "4. Checking HLS segment files..."
SEGMENT_FILES=$(docker exec tvchannel ls -1 /app/hls/*.ts 2>/dev/null | wc -l)
if [ "$SEGMENT_FILES" -gt 0 ]; then
    echo "   ✓ Found $SEGMENT_FILES segment file(s)"
    docker exec tvchannel ls -lh /app/hls/*.ts 2>/dev/null | head -5
else
    echo "   ✗ No segment files found!"
fi

echo ""
echo "5. Checking stream.py logs (last 30 lines)..."
docker logs tvchannel 2>&1 | grep -A 5 -B 5 "stream\|Streaming\|FFmpeg" | tail -30

echo ""
echo "6. Checking playlist file..."
if docker exec tvchannel test -f /app/server/playlist.txt; then
    echo "   ✓ Playlist file exists"
    PLAYLIST_LINES=$(docker exec tvchannel wc -l < /app/server/playlist.txt)
    echo "   Lines in playlist: $PLAYLIST_LINES"
    echo "   First 5 lines:"
    docker exec tvchannel head -5 /app/server/playlist.txt
else
    echo "   ✗ Playlist file does NOT exist!"
fi

echo ""
echo "=== Done ==="

