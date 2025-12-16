#!/bin/bash
# Check the tvshows dataset for actual TV shows

echo "=== Checking /mnt/blackhole/tvshows ==="
if [ -d "/mnt/blackhole/tvshows" ]; then
    echo "Contents:"
    ls -la /mnt/blackhole/tvshows/
    echo ""
    echo "All directories:"
    ls -1 /mnt/blackhole/tvshows/ 2>/dev/null | head -20
    echo ""
    echo "Searching for The Office:"
    find /mnt/blackhole/tvshows -type d -iname "*office*" 2>/dev/null
    echo ""
    echo "Total size:"
    du -sh /mnt/blackhole/tvshows/ 2>/dev/null
else
    echo "/mnt/blackhole/tvshows does not exist"
fi
echo ""

echo "=== Checking if TV shows are mixed in with movies ==="
find /mnt/blackhole/media/movies -type d -iname "*office*" 2>/dev/null
find /mnt/blackhole/media/movies -type d -iname "*the.office*" 2>/dev/null
echo ""

echo "=== Checking Plex configuration for library paths ==="
echo "Plex might tell us where it's reading TV shows from"
if [ -d "/mnt/.ix-apps/app_mounts/plex/config" ]; then
    echo "Looking for Plex library config..."
    find /mnt/.ix-apps/app_mounts/plex/config -name "*.xml" -o -name "*.db" 2>/dev/null | head -5
fi

