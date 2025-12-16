#!/bin/bash
# Broader search for The Office

echo "=== Checking what's actually in /mnt/blackhole/media ==="
if [ -d "/mnt/blackhole/media" ]; then
    echo "Contents of /mnt/blackhole/media:"
    ls -la /mnt/blackhole/media/ | head -20
    echo ""
    echo "Total items: $(ls -1 /mnt/blackhole/media/ | wc -l)"
else
    echo "/mnt/blackhole/media does not exist"
fi
echo ""

echo "=== Searching for any TV show directories ==="
find /mnt/blackhole -maxdepth 3 -type d -name "*" 2>/dev/null | grep -iE "(tv|show|series|media)" | head -20
echo ""

echo "=== Searching for common TV show naming patterns ==="
find /mnt/blackhole -type d -iname "*the*" 2>/dev/null | head -20
echo ""

echo "=== Checking Samba share locations ==="
echo "Checking /mnt/blackhole for Samba shares:"
ls -la /mnt/blackhole/ | grep -iE "(share|samba|media|tv)"
echo ""

echo "=== Looking for any .mkv or .mp4 files (sample) ==="
find /mnt/blackhole -type f \( -iname "*.mkv" -o -iname "*.mp4" \) 2>/dev/null | head -5 | xargs -I {} dirname {} | sort -u
echo ""

echo "=== Checking if Plex has a config that shows media location ==="
if [ -d "/mnt/blackhole/apps/plex" ]; then
    echo "Found Plex directory, checking config..."
    find /mnt/blackhole/apps/plex -name "*.conf" -o -name "*.xml" 2>/dev/null | head -5
fi

