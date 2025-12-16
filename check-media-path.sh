#!/bin/bash
# Check media path configuration and accessibility

echo "========================================="
echo "Media Path Diagnostic"
echo "========================================="
echo ""

# Check config file
echo "1. Checking channel config media_root:"
docker exec tvchannel cat /app/config/channel_settings.json | grep -A 2 "media_root" | head -5
echo ""

# Check if path exists inside container
echo "2. Checking if /media/tvchannel exists inside container:"
docker exec tvchannel ls -ld /media/tvchannel 2>&1
echo ""

# List contents of media directory
echo "3. Listing contents of /media/tvchannel (first 20 items):"
docker exec tvchannel ls -1 /media/tvchannel 2>&1 | head -20
echo ""

# Check if it's a directory
echo "4. Checking if /media/tvchannel is a directory:"
docker exec tvchannel test -d /media/tvchannel && echo "✓ Is a directory" || echo "✗ Not a directory or doesn't exist"
echo ""

# Check volume mount
echo "5. Checking Docker volume mounts:"
docker inspect tvchannel | grep -A 10 "Mounts" | grep -E "(Source|Destination|media)" | head -10
echo ""

# Test API discover endpoint
echo "6. Testing discover endpoint directly:"
docker exec tvchannel curl -s "http://localhost:8000/api/channels/main/shows/discover" 2>&1 | head -10
echo ""

# Check what channel ID exists
echo "7. Checking available channels:"
docker exec tvchannel curl -s "http://localhost:8000/api/channels" 2>&1 | python3 -m json.tool 2>/dev/null | grep -E "(id|media_root)" | head -10 || docker exec tvchannel curl -s "http://localhost:8000/api/channels" 2>&1 | head -10
echo ""

echo "========================================="
echo "If /media/tvchannel doesn't exist, check:"
echo "1. Volume mount in docker run command"
echo "2. Host path /mnt/blackhole/media/tv exists"
echo "3. Channel config has correct media_root"

