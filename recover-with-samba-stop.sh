#!/bin/bash
# Recovery script that stops Samba to unmount the dataset

echo "=== Recovery: Stopping Samba to access hidden data ==="
echo ""
echo "⚠️  WARNING: This will temporarily stop Samba file sharing"
echo "   Any active Samba connections will be interrupted"
echo ""

read -p "Do you want to proceed? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "1. Stopping Samba service..."
systemctl stop smbd 2>/dev/null || service smbd stop 2>/dev/null || echo "   Could not stop smbd (might not be running as service)"

echo "2. Waiting for processes to release..."
sleep 3

echo "3. Killing any remaining smbd processes using the directory..."
# Find PIDs using the directory
PIDS=$(lsof +D /mnt/blackhole/media/tv 2>/dev/null | grep smbd | awk '{print $2}' | sort -u)
if [ -n "$PIDS" ]; then
    for pid in $PIDS; do
        echo "   Killing smbd PID $pid"
        kill -9 $pid 2>/dev/null || true
    done
    sleep 2
fi

echo "4. Attempting to unmount..."
zfs unmount blackhole/media/tv

if [ $? -eq 0 ]; then
    echo "   ✓ Successfully unmounted!"
    echo ""
    
    echo "5. Checking what's now visible:"
    echo "   Listing /mnt/blackhole/media/tv:"
    ls -la /mnt/blackhole/media/tv/ 2>/dev/null | head -30
    echo ""
    
    echo "6. Checking for TV show directories:"
    find /mnt/blackhole/media/tv -maxdepth 1 -type d 2>/dev/null | head -30
    echo ""
    
    echo "7. Checking total size:"
    du -sh /mnt/blackhole/media/tv 2>/dev/null
    echo ""
    
    echo "8. Searching for The Office:"
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
        echo "=== RECOVERY STEPS ==="
        echo ""
        echo "1. Create a backup location:"
        echo "   mkdir -p /mnt/blackhole/media/tv_recovered"
        echo ""
        echo "2. Copy your shows (this may take a while):"
        echo "   cp -av /mnt/blackhole/media/tv/* /mnt/blackhole/media/tv_recovered/"
        echo ""
        echo "3. After copying, remount the dataset:"
        echo "   zfs mount blackhole/media/tv"
        echo ""
        echo "4. Restart Samba:"
        echo "   systemctl start smbd"
        echo ""
        echo "5. Then move shows to your preferred location"
    else
        echo "⚠️  No data found. The shows might be truly gone."
        echo ""
        echo "Remounting dataset and restarting Samba..."
        zfs mount blackhole/media/tv
        systemctl start smbd 2>/dev/null || service smbd start 2>/dev/null || true
    fi
else
    echo "   ✗ Still cannot unmount"
    echo ""
    echo "The dataset is still in use. Try:"
    echo "1. Check what's using it: lsof +D /mnt/blackhole/media/tv"
    echo "2. Disconnect any Samba clients"
    echo "3. Or reboot the system (will unmount everything)"
    
    # Try to restart Samba anyway
    systemctl start smbd 2>/dev/null || service smbd start 2>/dev/null || true
fi

