#!/bin/bash
# Force recovery by stopping services and unmounting

echo "=== Force Recovery: Stopping services and unmounting ==="
echo ""

echo "1. Checking what's using the dataset:"
echo "   Checking Docker containers..."
docker ps | grep tvchannel || echo "   No tvchannel container running"
echo ""

echo "2. Checking for open files:"
lsof +D /mnt/blackhole/media/tv 2>/dev/null | head -10 || echo "   No open files found (or lsof not available)"
echo ""

echo "3. Checking Samba shares:"
smbstatus 2>/dev/null | grep -i "media/tv" || echo "   No Samba shares using this path"
echo ""

echo "4. Stopping Docker container (if running)..."
docker stop tvchannel 2>/dev/null && echo "   ✓ Stopped tvchannel container" || echo "   Container not running"
echo ""

echo "5. Waiting a moment for processes to release..."
sleep 2
echo ""

echo "6. Attempting to unmount..."
zfs unmount blackhole/media/tv

if [ $? -eq 0 ]; then
    echo "   ✓ Successfully unmounted!"
    echo ""
    
    echo "7. Checking what's now visible:"
    echo "   Listing /mnt/blackhole/media/tv:"
    ls -la /mnt/blackhole/media/tv/ 2>/dev/null | head -30
    echo ""
    
    echo "8. Checking for TV show directories:"
    find /mnt/blackhole/media/tv -maxdepth 1 -type d 2>/dev/null | head -30
    echo ""
    
    echo "9. Checking total size:"
    du -sh /mnt/blackhole/media/tv 2>/dev/null
    echo ""
    
    echo "10. Searching for The Office:"
    find /mnt/blackhole/media/tv -type d -iname "*office*" 2>/dev/null
    echo ""
    
    echo "=== RESULT ==="
    TV_SIZE=$(du -sh /mnt/blackhole/media/tv 2>/dev/null | cut -f1)
    TV_COUNT=$(find /mnt/blackhole/media/tv -maxdepth 1 -type d 2>/dev/null | wc -l)
    
    if [ "$TV_SIZE" != "512" ] && [ "$TV_COUNT" -gt 1 ]; then
        echo "🎉 SUCCESS! Your TV shows are still there!"
        echo "   Size: $TV_SIZE"
        echo "   Directories found: $TV_COUNT"
        echo ""
        echo "Next steps:"
        echo "1. Copy them to a safe location:"
        echo "   mkdir -p /mnt/blackhole/media/tv_recovered"
        echo "   cp -av /mnt/blackhole/media/tv/* /mnt/blackhole/media/tv_recovered/"
        echo ""
        echo "2. After copying, remount the dataset:"
        echo "   zfs mount blackhole/media/tv"
        echo ""
        echo "3. Then move them to your preferred location"
    else
        echo "⚠️  No data found. The shows might be truly gone or in a different location."
        echo "   Remounting dataset..."
        zfs mount blackhole/media/tv
    fi
else
    echo "   ✗ Still cannot unmount"
    echo ""
    echo "Trying force unmount (risky but might work):"
    zfs unmount -f blackhole/media/tv
    
    if [ $? -eq 0 ]; then
        echo "   ✓ Force unmount successful!"
        echo "   Now check /mnt/blackhole/media/tv for your shows"
    else
        echo "   ✗ Force unmount also failed"
        echo "   The dataset might be in use by the system"
        echo "   Try rebooting or checking what process is using it"
    fi
fi

