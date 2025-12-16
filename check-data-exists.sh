#!/bin/bash
# Last-ditch check to see if data exists anywhere

echo "=== Checking if data might still exist ==="
echo ""

echo "1. Checking if old directory exists as a hidden mount:"
mount | grep -i tv
echo ""

echo "2. Checking all mount points:"
mount | grep blackhole
echo ""

echo "3. Checking if there's a .zfs hidden directory with data:"
if [ -d "/mnt/blackhole/media/.zfs" ]; then
    find /mnt/blackhole/media/.zfs -type f 2>/dev/null | head -10
fi
echo ""

echo "4. Checking ZFS dataset properties - when was it created:"
zfs get creation,used,referenced blackhole/media/tv
echo ""

echo "5. Checking if there are any other datasets that might contain the data:"
zfs list | grep -E "(media|tv)" | grep -v "tvchannel"
echo ""

echo "6. Checking disk usage - if tv dataset shows 0 used, data is likely gone:"
zfs get used blackhole/media/tv
echo ""

echo "=== If used=0, the data is likely unrecoverable without backups ==="
echo "=== Check your backup systems (external drives, cloud backup, etc.) ==="

