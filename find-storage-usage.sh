#!/bin/bash
# Find where the actual storage is being used

echo "=== Storage Usage Analysis ==="
echo ""

echo "1. Total pool usage breakdown:"
zfs list -o name,used,referenced,avail,usedbysnapshots | grep blackhole | head -20
echo ""

echo "2. Detailed breakdown of blackhole/media dataset:"
zfs list -r -o name,used,referenced,avail blackhole/media
echo ""

echo "3. Checking what's actually in /mnt/blackhole/media:"
ls -lah /mnt/blackhole/media/
echo ""

echo "4. Size of each subdirectory in /mnt/blackhole/media:"
du -sh /mnt/blackhole/media/* 2>/dev/null | sort -h
echo ""

echo "5. Checking if there are hidden directories or .zfs snapshots:"
if [ -d "/mnt/blackhole/media/.zfs" ]; then
    echo "Found .zfs directory - checking contents:"
    ls -la /mnt/blackhole/media/.zfs/
    if [ -d "/mnt/blackhole/media/.zfs/snapshot" ]; then
        echo "Snapshots found:"
        ls -la /mnt/blackhole/media/.zfs/snapshot/
        echo "Checking snapshot sizes:"
        for snap in /mnt/blackhole/media/.zfs/snapshot/*; do
            if [ -d "$snap" ]; then
                echo "  $(basename $snap): $(du -sh "$snap" 2>/dev/null | cut -f1)"
            fi
        done
    fi
fi
echo ""

echo "6. Checking if old directory structure exists under parent dataset:"
# Check if there's data in the parent that's not showing up
find /mnt/blackhole/media -maxdepth 2 -type d 2>/dev/null | head -20
echo ""

echo "7. Checking dataset properties for clues:"
zfs get all blackhole/media | grep -E "(used|referenced|written|logicalused)"
echo ""

echo "8. Looking for large files/directories:"
find /mnt/blackhole/media -type f -size +1G 2>/dev/null | head -10
echo ""

echo "=== KEY INSIGHT ==="
echo "If 'blackhole/media' shows high 'used' but 'blackhole/media/tv' shows low 'used',"
echo "the data might be in the parent dataset or in a hidden location."
echo ""
echo "Check: zfs list -r blackhole/media"
echo "This will show if data is in the parent vs child dataset."

