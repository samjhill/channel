#!/bin/bash
# Check Samba shares and actual media locations

echo "=== Checking parent directory /mnt/blackhole/media ==="
ls -la /mnt/blackhole/media/
echo ""

echo "=== Checking for Samba share configuration ==="
# Check TrueNAS Samba config
if [ -f "/etc/smb4.conf" ]; then
    echo "Samba config found:"
    grep -E "^\[|path\s*=" /etc/smb4.conf | head -20
fi
echo ""

echo "=== Checking all datasets in blackhole pool ==="
zfs list | grep blackhole
echo ""

echo "=== Checking what's mounted ==="
mount | grep blackhole
echo ""

echo "=== Checking for media in common locations ==="
for dir in /mnt/blackhole/media /mnt/blackhole/tvshows /mnt/blackhole/shared /mnt/blackhole/shares; do
    if [ -d "$dir" ]; then
        echo "Contents of $dir:"
        ls -la "$dir" | head -10
        echo ""
    fi
done

echo "=== Checking if /mnt/blackhole/media has subdirectories ==="
find /mnt/blackhole/media -maxdepth 2 -type d 2>/dev/null | head -20
echo ""

echo "=== Checking for any video files to find actual location ==="
find /mnt/blackhole -type f \( -iname "*.mkv" -o -iname "*.mp4" -o -iname "*.avi" \) 2>/dev/null | head -3 | while read file; do
    echo "Found: $file"
    echo "  Directory: $(dirname "$file")"
done

