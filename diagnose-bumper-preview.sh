#!/bin/bash
# Diagnose bumper preview generation issues

echo "=== Bumper Preview Diagnostics ==="
echo ""

echo "1. Checking if API is responding..."
API_RESPONSE=$(curl -s -w "\n%{http_code}" "http://localhost:8000/api/bumper-preview/next" 2>&1)
HTTP_CODE=$(echo "$API_RESPONSE" | tail -n1)
BODY=$(echo "$API_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
    echo "✓ API responded successfully"
    echo "Response preview:"
    echo "$BODY" | head -c 200
    echo "..."
elif [ "$HTTP_CODE" = "504" ]; then
    echo "✗ API timed out (504) - preview generation is taking too long"
elif [ "$HTTP_CODE" = "500" ]; then
    echo "✗ API returned 500 error"
    echo "Error details:"
    echo "$BODY"
else
    echo "✗ API returned HTTP $HTTP_CODE"
    echo "Response:"
    echo "$BODY"
fi
echo ""

echo "2. Checking container logs for preview errors..."
docker logs tvchannel 2>&1 | grep -i "preview\|bumper.*preview\|FFmpeg.*preview" | tail -20
echo ""

echo "3. Checking if preview video files exist..."
docker exec tvchannel ls -lah /app/hls/preview_block_*.mp4 2>/dev/null | tail -5 || echo "No preview files found"
echo ""

echo "4. Checking if HLS directory is writable..."
docker exec tvchannel test -w /app/hls && echo "✓ HLS directory is writable" || echo "✗ HLS directory is NOT writable"
echo ""

echo "5. Checking if FFmpeg is available..."
docker exec tvchannel which ffmpeg && echo "✓ FFmpeg found" || echo "✗ FFmpeg not found"
echo ""

echo "6. Checking if bumper block generator is working..."
docker exec tvchannel python3 -c "
import sys
sys.path.insert(0, '/app')
from server.bumper_block import get_generator
gen = get_generator()
block = gen.peek_next_pregenerated_block()
if block:
    print(f'✓ Found pre-generated block with {len(block.bumpers)} bumpers')
    print(f'  Block ID: {block.block_id}')
    print(f'  Music: {block.music_track}')
else:
    print('✗ No pre-generated blocks found')
" 2>&1
echo ""

echo "=== Done ==="

