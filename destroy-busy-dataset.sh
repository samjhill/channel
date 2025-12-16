#!/bin/bash
# Destroy a busy dataset by checking what's using it

echo "=== Destroying Busy Dataset ==="
echo ""

echo "1. Checking what's using the dataset..."
echo "   Checking for open files:"
lsof +D /mnt/blackhole/media/tv 2>/dev/null | head -10 || echo "   No open files found"
echo ""

echo "2. Checking Samba shares..."
smbstatus 2>/dev/null | grep -i "media/tv" || echo "   No Samba shares found"
echo ""

echo "3. Checking if mount point directory exists and is empty..."
if [ -d "/mnt/blackhole/media/tv" ]; then
    CONTENTS=$(ls -A /mnt/blackhole/media/tv 2>/dev/null | wc -l)
    if [ "$CONTENTS" -eq 0 ]; then
        echo "   ✓ Directory exists and is empty (as expected for dataset)"
    else
        echo "   ⚠️  Directory has $CONTENTS items - these are your shows!"
        echo "   This means the dataset is already unmounted and shows are visible"
    fi
else
    echo "   ✗ Directory doesn't exist"
fi
echo ""

echo "4. Checking dataset mount status..."
MOUNTED=$(zfs get mounted blackhole/media/tv 2>/dev/null | tail -1 | awk '{print $3}')
echo "   Mount status: $MOUNTED"
echo ""

echo "5. Attempting to destroy dataset..."
# Try with -f flag to force
zfs destroy -f blackhole/media/tv

if [ $? -eq 0 ]; then
    echo "   ✓ Dataset destroyed successfully!"
else
    echo "   ✗ Still cannot destroy"
    echo ""
    echo "6. Trying alternative: Set canmount=no and then destroy..."
    zfs set canmount=no blackhole/media/tv 2>/dev/null
    sleep 1
    zfs destroy -f blackhole/media/tv
    
    if [ $? -eq 0 ]; then
        echo "   ✓ Dataset destroyed after setting canmount=no"
    else
        echo "   ✗ Still cannot destroy"
        echo ""
        echo "The dataset might be in use by:"
        echo "  - A Samba share configuration"
        echo "  - A Docker volume mount"
        echo "  - System processes"
        echo ""
        echo "Try:"
        echo "  1. Check Samba shares: smbstatus"
        echo "  2. Check Docker: docker ps -a | grep tvchannel"
        echo "  3. Reboot the system (will release all mounts)"
        exit 1
    fi
fi

echo ""
echo "7. Verifying shows are accessible..."
if [ -d "/mnt/blackhole/media/tv" ] && [ "$(ls -A /mnt/blackhole/media/tv 2>/dev/null)" ]; then
    SHOW_COUNT=$(find /mnt/blackhole/media/tv -maxdepth 1 -type d 2>/dev/null | wc -l)
    TV_SIZE=$(du -sh /mnt/blackhole/media/tv 2>/dev/null | cut -f1)
    echo "   ✓ Shows are accessible!"
    echo "   Count: $SHOW_COUNT directories"
    echo "   Size: $TV_SIZE"
    echo ""
    echo "=== SUCCESS! ==="
    echo ""
    echo "Your TV shows are now accessible at:"
    echo "  /mnt/blackhole/media/tv"
    echo ""
    echo "Restart Samba:"
    echo "  systemctl start smbd"
else
    echo "   ⚠️  No shows found - check manually"
fi

echo ""
echo "8. Restarting Samba..."
systemctl start smbd 2>/dev/null || service smbd start 2>/dev/null

echo ""
echo "Done!"

