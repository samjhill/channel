#!/bin/bash
# Find where media files actually are

echo "========================================="
echo "Finding Actual Media Location"
echo "========================================="
echo ""

# Check Samba shares
echo "1. Checking Samba share paths:"
midclt call smb.shares.query 2>/dev/null | python3 -m json.tool 2>/dev/null | grep -E "(name|path)" | head -20 || {
    echo "Trying alternative method..."
    midclt call smb.shares.query 2>&1 | grep -E "(name|path)" | head -20
}
echo ""

# Check what's actually in /mnt/blackhole
echo "2. Checking /mnt/blackhole structure:"
ls -la /mnt/blackhole/ 2>&1
echo ""

# Check for media in common locations
echo "3. Checking common media locations:"
for path in /mnt/blackhole/media /mnt/blackhole/shared /mnt/blackhole/media/tv /mnt/blackhole/shared/media; do
    if [ -d "$path" ]; then
        echo "  $path exists:"
        ls -1 "$path" 2>&1 | head -5
        echo ""
    fi
done

# Check all datasets
echo "4. Checking all datasets for media-related names:"
zfs list | grep -E "(NAME|media|shared|tv)" | head -20
echo ""

# Check if /mnt/blackhole/media/tv is a symlink or mount
echo "5. Checking if /mnt/blackhole/media/tv is a symlink:"
ls -ld /mnt/blackhole/media/tv 2>&1
file /mnt/blackhole/media/tv 2>&1
echo ""

# Check Plex media paths (if Plex is configured)
echo "6. Checking for Plex configuration (if accessible):"
if [ -d "/mnt/blackhole/apps/plex" ] || [ -d "/mnt/apps/applications/plex" ]; then
    echo "Plex directory found, checking config..."
    find /mnt -name "Preferences.xml" -path "*/plex*" 2>/dev/null | head -3
else
    echo "Plex config not found in standard locations"
fi
echo ""

echo "========================================="
echo "Next steps:"
echo "1. Check Samba share paths above (step 1)"
echo "2. Find where Plex is reading media from"
echo "3. Update docker-compose.truenas.yml with correct path"
echo "4. Restart container"

