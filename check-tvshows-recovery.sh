#!/bin/bash
# Check if TV shows are in the tvshows dataset

echo "=== Checking blackhole/tvshows dataset ==="
echo ""

echo "1. Dataset properties:"
zfs get used,referenced,creation blackhole/tvshows
echo ""

echo "2. Contents of /mnt/blackhole/tvshows:"
ls -la /mnt/blackhole/tvshows/
echo ""

echo "3. All directories in tvshows:"
find /mnt/blackhole/tvshows -maxdepth 2 -type d 2>/dev/null | head -20
echo ""

echo "4. Searching for The Office:"
find /mnt/blackhole/tvshows -type d -iname "*office*" 2>/dev/null
echo ""

echo "5. Total size and file count:"
du -sh /mnt/blackhole/tvshows/ 2>/dev/null
find /mnt/blackhole/tvshows -type f 2>/dev/null | wc -l
echo ""

echo "6. Sample files (if any):"
find /mnt/blackhole/tvshows -type f \( -iname "*.mkv" -o -iname "*.mp4" \) 2>/dev/null | head -5
echo ""

echo "=== If tvshows is empty, check when it was created vs when media/tv was created ==="
echo "tvshows creation:"
zfs get creation blackhole/tvshows | tail -1
echo "media/tv creation:"
zfs get creation blackhole/media/tv | tail -1

