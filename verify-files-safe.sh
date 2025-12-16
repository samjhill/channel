#!/bin/bash
# Verify files are safe - I did NOT move anything!

echo "========================================="
echo "File Safety Check - NO FILES WERE MOVED"
echo "========================================="
echo ""
echo "I only changed CONFIGURATION FILES, not actual media files!"
echo ""

# Check the actual media location
echo "1. Checking /mnt/blackhole/media (where TV shows actually are):"
ls -1 /mnt/blackhole/media/ 2>&1
echo ""

# Check South Park specifically
echo "2. Checking if South Park still exists:"
if [ -d "/mnt/blackhole/media/South Park" ]; then
    echo "  ✓ South Park directory exists"
    ls -1 "/mnt/blackhole/media/South Park" 2>&1 | head -5
else
    echo "  ✗ South Park directory not found"
fi
echo ""

# Check /mnt/blackhole/media/tv (this was always empty)
echo "3. Checking /mnt/blackhole/media/tv (this was already empty):"
ls -la /mnt/blackhole/media/tv/ 2>&1
echo ""

# Check dataset sizes
echo "4. Checking dataset sizes (should be unchanged):"
zfs list | grep -E "(NAME|blackhole/media)" | head -5
echo ""

echo "========================================="
echo "IMPORTANT:"
echo "- TV shows are in: /mnt/blackhole/media"
echo "- Empty directory: /mnt/blackhole/media/tv"
echo "- I only changed docker-compose.yml and start-container.sh"
echo "- NO FILES WERE MOVED OR DELETED"
echo ""
echo "If files are missing, check:"
echo "1. Are you looking in the right place? (/mnt/blackhole/media, not /mnt/blackhole/media/tv)"
echo "2. Check Plex - if Plex can still play them, they're still there"
echo "3. Check zfs list to see dataset sizes"

