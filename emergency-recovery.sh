#!/bin/bash
# Emergency recovery script - check if data can be recovered

echo "=== CRITICAL: Checking for data recovery options ==="
echo ""

echo "1. Checking ZFS dataset history for blackhole/media/tv:"
zfs get all blackhole/media/tv 2>/dev/null | grep -E "(creation|mountpoint|origin)" || echo "Dataset info not available"
echo ""

echo "2. Checking if there's a parent snapshot or clone:"
zfs list -t all | grep "blackhole/media" | head -10
echo ""

echo "3. Checking if the old dataset still exists with a different name:"
zfs list | grep -E "(media|tv)" | grep -v "tvchannel"
echo ""

echo "4. Checking ZFS history/transactions (if available):"
# Some systems log ZFS operations
dmesg | grep -i zfs | tail -20 || echo "No ZFS messages in dmesg"
echo ""

echo "5. Checking if there are any hidden .zfs directories with snapshots:"
if [ -d "/mnt/blackhole/media/.zfs" ]; then
    echo "Found .zfs directory - checking snapshots:"
    ls -la /mnt/blackhole/media/.zfs/snapshot/ 2>/dev/null || echo "No snapshots found"
fi
echo ""

echo "6. Checking when the tv dataset was created:"
zfs get creation blackhole/media/tv 2>/dev/null
echo ""

echo "7. Checking if there's a backup or previous version:"
# Check common backup locations
for backup in /mnt/blackhole/backups /mnt/blackhole/.zfs/snapshot; do
    if [ -d "$backup" ]; then
        echo "Checking $backup:"
        find "$backup" -type d -iname "*tv*" -o -iname "*office*" 2>/dev/null | head -5
    fi
done
echo ""

echo "=== IMMEDIATE ACTIONS ==="
echo "1. DO NOT create or modify any more datasets"
echo "2. Check TrueNAS web UI for snapshots"
echo "3. Check if TrueNAS has automatic snapshots enabled"
echo "4. Contact TrueNAS support if snapshots exist"
echo ""
echo "=== If snapshots exist, you can restore with: ==="
echo "zfs rollback blackhole/media/tv@snapshot-name"
echo ""
echo "=== Check TrueNAS web UI: ==="
echo "Storage -> Snapshots -> Look for blackhole/media/tv snapshots"

