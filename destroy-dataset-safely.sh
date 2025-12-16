#!/bin/bash
# Safely destroy the empty dataset to reveal the shows

echo "=== Safely Destroying Empty Dataset ==="
echo ""
echo "This will:"
echo "1. Stop Samba"
echo "2. Unmount the dataset"
echo "3. Destroy the empty dataset"
echo "4. Your shows will remain visible at /mnt/blackhole/media/tv"
echo "5. Restart Samba"
echo ""

read -p "Proceed? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "1. Stopping Samba..."
systemctl stop smbd 2>/dev/null || service smbd stop 2>/dev/null
sleep 2

# Kill any remaining smbd processes
PIDS=$(lsof +D /mnt/blackhole/media/tv 2>/dev/null | grep smbd | awk '{print $2}' | sort -u)
if [ -n "$PIDS" ]; then
    for pid in $PIDS; do
        kill -9 $pid 2>/dev/null || true
    done
    sleep 2
fi

echo "2. Unmounting dataset..."
zfs unmount blackhole/media/tv

if [ $? -ne 0 ]; then
    echo "   ⚠️  Unmount failed, trying force..."
    zfs unmount -f blackhole/media/tv
fi

if [ $? -ne 0 ]; then
    echo "   ✗ Cannot unmount dataset"
    echo "   Try: lsof +D /mnt/blackhole/media/tv"
    exit 1
fi

echo "   ✓ Dataset unmounted"
echo ""

echo "3. Verifying shows are visible..."
if [ -d "/mnt/blackhole/media/tv" ] && [ "$(ls -A /mnt/blackhole/media/tv 2>/dev/null)" ]; then
    SHOW_COUNT=$(find /mnt/blackhole/media/tv -maxdepth 1 -type d 2>/dev/null | wc -l)
    echo "   ✓ Shows are visible ($SHOW_COUNT directories found)"
else
    echo "   ⚠️  Warning: No shows found - aborting destroy!"
    echo "   Remounting dataset..."
    zfs mount blackhole/media/tv
    systemctl start smbd 2>/dev/null || service smbd start 2>/dev/null
    exit 1
fi

echo ""
echo "4. Destroying empty dataset..."
zfs destroy blackhole/media/tv

if [ $? -eq 0 ]; then
    echo "   ✓ Dataset destroyed successfully"
else
    echo "   ✗ Failed to destroy dataset"
    echo "   Remounting..."
    zfs mount blackhole/media/tv
    systemctl start smbd 2>/dev/null || service smbd start 2>/dev/null
    exit 1
fi

echo ""
echo "5. Verifying shows are still accessible..."
if [ -d "/mnt/blackhole/media/tv" ] && [ "$(ls -A /mnt/blackhole/media/tv 2>/dev/null)" ]; then
    SHOW_COUNT=$(find /mnt/blackhole/media/tv -maxdepth 1 -type d 2>/dev/null | wc -l)
    TV_SIZE=$(du -sh /mnt/blackhole/media/tv 2>/dev/null | cut -f1)
    echo "   ✓ Shows are still there!"
    echo "   Count: $SHOW_COUNT directories"
    echo "   Size: $TV_SIZE"
else
    echo "   ✗ ERROR: Shows disappeared!"
    echo "   This should not happen - the shows should remain in parent dataset"
    exit 1
fi

echo ""
echo "6. Restarting Samba..."
systemctl start smbd 2>/dev/null || service smbd start 2>/dev/null
sleep 2

echo ""
echo "=== SUCCESS! ==="
echo ""
echo "Your TV shows are now accessible at:"
echo "  /mnt/blackhole/media/tv"
echo ""
echo "The empty dataset has been destroyed."
echo "Your shows are now in the parent dataset (blackhole/media)."
echo ""
echo "Next: Update docker-compose.truenas.yml to use:"
echo "  - /mnt/blackhole/media/tv:/media/tvchannel:ro"
echo ""
echo "Current status:"
zfs list blackhole/media | tail -1
ls -1 /mnt/blackhole/media/tv | head -10

