#!/bin/bash
# Complete the recovery process after copying shows

echo "=== Completing Recovery Process ==="
echo ""

echo "1. Checking recovery location..."
if [ -d "/mnt/blackhole/media/tv_recovered" ]; then
    RECOVERED_SIZE=$(du -sh /mnt/blackhole/media/tv_recovered 2>/dev/null | cut -f1)
    RECOVERED_COUNT=$(find /mnt/blackhole/media/tv_recovered -maxdepth 1 -type d 2>/dev/null | wc -l)
    echo "   ✓ Recovery location found"
    echo "   Size: $RECOVERED_SIZE"
    echo "   Shows: $RECOVERED_COUNT"
else
    echo "   ✗ Recovery location not found"
    echo "   Make sure the copy completed successfully"
    exit 1
fi

echo ""
echo "2. Remounting the dataset..."
zfs mount blackhole/media/tv

if [ $? -eq 0 ]; then
    echo "   ✓ Dataset remounted successfully"
else
    echo "   ✗ Failed to remount dataset"
    exit 1
fi

echo ""
echo "3. Restarting Samba..."
systemctl start smbd 2>/dev/null || service smbd start 2>/dev/null

if [ $? -eq 0 ]; then
    echo "   ✓ Samba restarted"
else
    echo "   ⚠️  Samba might already be running or failed to start"
fi

echo ""
echo "=== Recovery Complete! ==="
echo ""
echo "Your TV shows are now safely copied to:"
echo "  /mnt/blackhole/media/tv_recovered"
echo ""
echo "Next steps:"
echo ""
echo "Option 1: Keep shows in recovered location"
echo "  Update docker-compose.truenas.yml to use:"
echo "    - /mnt/blackhole/media/tv_recovered:/media/tvchannel:ro"
echo ""
echo "Option 2: Move shows to the dataset location"
echo "  mv /mnt/blackhole/media/tv_recovered/* /mnt/blackhole/media/tv/"
echo "  (This will put them in the dataset, accessible at /mnt/blackhole/media/tv)"
echo ""
echo "Option 3: Move shows to a different location"
echo "  Choose your preferred location and move them there"
echo ""
echo "Current dataset status:"
zfs list blackhole/media/tv | tail -1
echo ""
echo "Recovery location status:"
du -sh /mnt/blackhole/media/tv_recovered

