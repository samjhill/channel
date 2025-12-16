#!/bin/bash
# Check if there's enough space for the recovery

echo "=== Disk Space Check ==="
echo ""

echo "1. Current pool usage:"
zfs list blackhole | grep -E "NAME|blackhole$"
echo ""

echo "2. Available space:"
AVAIL=$(zfs get -Hp avail blackhole | awk '{print $3}')
AVAIL_TB=$(echo "scale=2; $AVAIL / 1024 / 1024 / 1024 / 1024" | bc)
echo "   Available: $AVAIL_TB TiB"
echo ""

echo "3. Recovery location space:"
if [ -d "/mnt/blackhole/media/tv_recovered" ]; then
    RECOVERED_SIZE=$(du -sb /mnt/blackhole/media/tv_recovered 2>/dev/null | cut -f1)
    RECOVERED_TB=$(echo "scale=2; $RECOVERED_SIZE / 1024 / 1024 / 1024 / 1024" | bc)
    echo "   Currently copied: $RECOVERED_TB TiB"
else
    RECOVERED_TB=0
fi

echo ""
echo "4. Source data size:"
SOURCE_SIZE=$(du -sb /mnt/blackhole/media/tv 2>/dev/null | cut -f1)
SOURCE_TB=$(echo "scale=2; $SOURCE_SIZE / 1024 / 1024 / 1024 / 1024" | bc)
echo "   Source: $SOURCE_TB TiB"
echo ""

echo "5. Space calculation:"
NEEDED_TB=$(echo "scale=2; $SOURCE_TB - $RECOVERED_TB" | bc)
echo "   Still needed: $NEEDED_TB TiB"
echo "   Available: $AVAIL_TB TiB"
echo ""

if (( $(echo "$NEEDED_TB <= $AVAIL_TB" | bc -l) )); then
    echo "✅ YES - You have enough space!"
    echo "   You can continue copying."
else
    echo "❌ NO - Not enough space!"
    echo "   Needed: $NEEDED_TB TiB"
    echo "   Available: $AVAIL_TB TiB"
    echo "   Shortfall: $(echo "scale=2; $NEEDED_TB - $AVAIL_TB" | bc) TiB"
    echo ""
    echo "=== ALTERNATIVE SOLUTION ==="
    echo ""
    echo "Since your shows are already in the parent dataset filesystem,"
    echo "you can skip copying and just destroy the empty child dataset:"
    echo ""
    echo "1. Stop the current copy (Ctrl+C)"
    echo "2. Destroy the empty dataset:"
    echo "   zfs destroy blackhole/media/tv"
    echo "3. Your shows will remain visible at /mnt/blackhole/media/tv"
    echo "4. No copy needed - they're already there!"
    echo ""
    echo "This is SAFER and FASTER than copying 5.4T!"
fi

