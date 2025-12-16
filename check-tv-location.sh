#!/bin/bash
# Check where TV shows actually are

echo "========================================="
echo "Finding TV Shows Location"
echo "========================================="
echo ""

# Check /mnt/blackhole/media
echo "1. Contents of /mnt/blackhole/media:"
ls -1 /mnt/blackhole/media/ 2>&1
echo ""

# Check if South Park has episodes
echo "2. Checking South Park (example show):"
if [ -d "/mnt/blackhole/media/South Park" ]; then
    echo "  Found South Park directory:"
    ls -1 "/mnt/blackhole/media/South Park" 2>&1 | head -10
    echo ""
    # Check for season directories
    find "/mnt/blackhole/media/South Park" -maxdepth 2 -type d 2>&1 | head -10
fi
echo ""

# Check /mnt/blackhole/tvshows
echo "3. Contents of /mnt/blackhole/tvshows:"
ls -1 /mnt/blackhole/tvshows/ 2>&1
echo ""

# Check /mnt/blackhole/media/tv
echo "4. Contents of /mnt/blackhole/media/tv:"
ls -1 /mnt/blackhole/media/tv/ 2>&1
echo ""

# Find all directories that might contain TV shows
echo "5. Finding directories with 'Season' or episode patterns:"
find /mnt/blackhole/media -maxdepth 2 -type d -name "*Season*" 2>&1 | head -10
echo ""

echo "========================================="
echo "Based on the output:"
echo "- If TV shows are in /mnt/blackhole/media directly, use:"
echo "  -v /mnt/blackhole/media:/media/tvchannel:ro"
echo ""
echo "- If TV shows are in /mnt/blackhole/tvshows, use:"
echo "  -v /mnt/blackhole/tvshows:/media/tvchannel:ro"
echo ""
echo "- If TV shows are in /mnt/blackhole/media/tv, check why it's empty"

