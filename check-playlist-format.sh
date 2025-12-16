#!/bin/bash
# Check HLS playlist format

echo "=== HLS Playlist Format Check ==="
echo ""

if ! docker ps | grep -q tvchannel; then
    echo "Container is not running"
    exit 1
fi

echo "1. Full playlist contents:"
docker exec tvchannel cat /app/hls/stream.m3u8

echo ""
echo "2. Checking for issues..."
PLAYLIST=$(docker exec tvchannel cat /app/hls/stream.m3u8)

# Count discontinuities
DISCONT_COUNT=$(echo "$PLAYLIST" | grep -c "EXT-X-DISCONTINUITY" || echo "0")
echo "   Discontinuity markers: $DISCONT_COUNT"

# Count segments
SEGMENT_COUNT=$(echo "$PLAYLIST" | grep -c "^stream" || echo "0")
echo "   Segment entries: $SEGMENT_COUNT"

# Check media sequence
MEDIA_SEQ=$(echo "$PLAYLIST" | grep "EXT-X-MEDIA-SEQUENCE" | cut -d: -f2 | tr -d ' ' || echo "none")
echo "   Media sequence: $MEDIA_SEQ"

# Check if segments are accessible via HTTP
echo ""
echo "3. Testing segment accessibility via nginx..."
SEGMENT=$(echo "$PLAYLIST" | grep "^stream" | head -1)
if [ -n "$SEGMENT" ]; then
    echo "   Testing: http://localhost:8080/channel/$SEGMENT"
    HTTP_CODE=$(docker exec tvchannel curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080/channel/$SEGMENT" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "   ✓ Segment is accessible"
    else
        echo "   ✗ Segment returned HTTP $HTTP_CODE"
    fi
fi

echo ""
echo "=== Done ==="

