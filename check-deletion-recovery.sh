#!/bin/bash
# Check for file recovery options and verify what happened

echo "=== CRITICAL: Checking for file recovery options ==="
echo ""

echo "1. Checking ZFS snapshots (these can restore deleted files):"
zfs list -t snapshot | grep blackhole/media || echo "No snapshots found"
echo ""

echo "2. Checking if files are in trash/recycle bin:"
# Check common trash locations
for trash in ~/.Trash /mnt/blackhole/.zfs/snapshot /mnt/blackhole/media/.zfs/snapshot; do
    if [ -d "$trash" ]; then
        echo "Found: $trash"
        ls -la "$trash" | head -10
    fi
done
echo ""

echo "3. Checking Docker container logs for any deletion activity:"
echo "Recent logs from tvchannel container:"
docker logs tvchannel 2>&1 | grep -iE "(delete|remove|rm|unlink|cleanup)" | tail -20 || echo "No deletion-related logs found"
echo ""

echo "4. Checking what the application actually accesses (from logs):"
docker logs tvchannel 2>&1 | grep -iE "(media|episode|\.mkv|\.mp4)" | tail -30 || echo "No media access logs found"
echo ""

echo "5. Verifying Docker volume mount configuration:"
docker inspect tvchannel 2>/dev/null | grep -A 10 "Mounts" || echo "Could not inspect container"
echo ""

echo "=== IMPORTANT NOTES ==="
echo "1. This application NEVER deletes media files - it only reads them"
echo "2. The application only cleans up HLS streaming segments (.ts files)"
echo "3. If files are truly gone, check ZFS snapshots for recovery"
echo "4. Check if files might be in a different location"
echo ""
echo "=== To recover from ZFS snapshot (if available) ==="
echo "zfs list -t snapshot | grep blackhole/media"
echo "# Then restore: zfs rollback blackhole/media@snapshot-name"

