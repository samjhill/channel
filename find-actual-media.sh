#!/bin/bash
# Find where the actual media files are located

echo "=== Checking if shows are in /mnt/blackhole/media/movies ==="
if [ -d "/mnt/blackhole/media/movies" ]; then
    echo "Contents of /mnt/blackhole/media/movies:"
    ls -1 /mnt/blackhole/media/movies/ | head -20
    echo ""
    echo "Searching for The Office:"
    find /mnt/blackhole/media/movies -maxdepth 1 -type d -iname "*office*" 2>/dev/null
    echo ""
fi

echo "=== Checking Docker container status and mounts ==="
if docker ps | grep -q tvchannel; then
    echo "Container is running. Checking mounts:"
    docker inspect tvchannel 2>/dev/null | jq '.[0].Mounts' 2>/dev/null || docker inspect tvchannel 2>/dev/null | grep -A 20 "Mounts"
else
    echo "Container is not running"
fi
echo ""

echo "=== Checking all datasets in blackhole pool ==="
zfs list | grep blackhole
echo ""

echo "=== Searching entire blackhole pool for video files ==="
echo "This will take a moment..."
find /mnt/blackhole -type f \( -iname "*.mkv" -o -iname "*.mp4" -o -iname "*.avi" \) 2>/dev/null | head -5 | while read file; do
    echo "Found: $file"
    echo "  Directory: $(dirname "$file")"
done
echo ""

echo "=== Checking Samba share paths ==="
if [ -f "/etc/smb4.conf" ]; then
    echo "Samba shares configured:"
    grep -E "^\[|path\s*=" /etc/smb4.conf | grep -v "^#" | head -10
fi
echo ""

echo "=== IMPORTANT: Check Plex library paths ==="
echo "Since Plex can play episodes, check Plex's library configuration"
echo "to see where it's actually reading files from."

