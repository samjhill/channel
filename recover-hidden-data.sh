#!/bin/bash
# Attempt to recover data that might be hidden by dataset mount point

echo "=== Attempting to recover hidden TV shows ==="
echo ""

echo "1. Current state:"
echo "   Parent dataset (blackhole/media): 6.67T used"
echo "   Child dataset (blackhole/media/tv): 96K used"
echo "   This suggests data is in parent but hidden by child mount"
echo ""

echo "2. Checking if we can temporarily unmount the child dataset:"
echo "   WARNING: This will temporarily hide /mnt/blackhole/media/tv"
echo "   But it might reveal the old directory structure"
echo ""

read -p "Do you want to proceed with unmounting blackhole/media/tv? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "3. Unmounting blackhole/media/tv dataset..."
zfs unmount blackhole/media/tv

if [ $? -eq 0 ]; then
    echo "   ✓ Successfully unmounted"
    echo ""
    
    echo "4. Checking what's now visible in /mnt/blackhole/media/tv:"
    ls -la /mnt/blackhole/media/tv/ 2>/dev/null | head -20
    echo ""
    
    echo "5. Checking for TV show directories:"
    find /mnt/blackhole/media/tv -maxdepth 1 -type d 2>/dev/null | head -20
    echo ""
    
    echo "6. Checking total size:"
    du -sh /mnt/blackhole/media/tv 2>/dev/null
    echo ""
    
    echo "7. Searching for The Office:"
    find /mnt/blackhole/media/tv -type d -iname "*office*" 2>/dev/null
    echo ""
    
    echo "=== IMPORTANT ==="
    echo "If you see your TV shows above, they're still there!"
    echo "We need to:"
    echo "1. Copy/move them to a safe location"
    echo "2. Then remount the dataset"
    echo ""
    
    read -p "Do you see your TV shows? (yes/no): " -r
    if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo ""
        echo "Great! Your shows are still there."
        echo "Next steps:"
        echo "1. Copy them to a temporary location:"
        echo "   mkdir -p /mnt/blackhole/media/tv_backup"
        echo "   cp -r /mnt/blackhole/media/tv/* /mnt/blackhole/media/tv_backup/"
        echo ""
        echo "2. Then remount the dataset:"
        echo "   zfs mount blackhole/media/tv"
        echo ""
        echo "3. Then move them back or to your preferred location"
    else
        echo ""
        echo "The data might be in a different location or truly gone."
        echo "Remounting the dataset..."
        zfs mount blackhole/media/tv
    fi
else
    echo "   ✗ Failed to unmount (might be in use)"
    echo "   Try stopping any services using it first"
fi

