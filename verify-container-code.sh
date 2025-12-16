#!/bin/bash
# Verify the code in the container matches what's in the repo

echo "=== Verifying Container Code ==="
echo ""

if ! docker ps | grep -q tvchannel; then
    echo "Container is not running"
    exit 1
fi

echo "1. Checking line 281 in container's stream.py..."
CONTAINER_LINE=$(docker exec tvchannel sed -n '281p' /app/server/stream.py 2>/dev/null)
echo "   Container line 281: $CONTAINER_LINE"

echo ""
echo "2. Checking line 281 in local stream.py..."
LOCAL_LINE=$(sed -n '281p' server/stream.py 2>/dev/null)
echo "   Local line 281: $LOCAL_LINE"

echo ""
echo "3. Checking for global declarations around line 281..."
docker exec tvchannel sed -n '275,290p' /app/server/stream.py 2>/dev/null | grep -n "global\|_current_ffmpeg_process"

echo ""
echo "4. Checking git commit in container..."
docker exec tvchannel cat /app/.git/HEAD 2>/dev/null || echo "   No git info in container"

echo ""
echo "5. Checking file modification time..."
docker exec tvchannel stat /app/server/stream.py 2>/dev/null | grep Modify

echo ""
if [ "$CONTAINER_LINE" != "$LOCAL_LINE" ]; then
    echo "❌ Container has different code than local!"
    echo "   Container needs to be rebuilt"
else
    echo "✓ Container code matches local"
fi

