#!/bin/bash
# Find The Office - US

echo "Searching for 'The Office'..."

# Search in /mnt/blackhole/media
echo "1. Searching in /mnt/blackhole/media:"
find /mnt/blackhole/media -type d -iname "*office*" 2>/dev/null
echo ""

# Search in /mnt/blackhole/tvshows
echo "2. Searching in /mnt/blackhole/tvshows:"
find /mnt/blackhole/tvshows -type d -iname "*office*" 2>/dev/null
echo ""

# List all directories in media to see naming
echo "3. All directories in /mnt/blackhole/media:"
ls -1 /mnt/blackhole/media/ | grep -i office
echo ""

# Search more broadly
echo "4. Searching entire blackhole pool:"
find /mnt/blackhole -type d -iname "*office*" 2>/dev/null | head -10
echo ""

# Check if it's in a subdirectory
echo "5. Checking for 'The Office' variations:"
ls -1 /mnt/blackhole/media/ | grep -iE "(office|the.office)" 
echo ""

echo "If found, note the exact path and update docker volume mount accordingly"

