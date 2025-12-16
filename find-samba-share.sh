#!/bin/bash
# Quick script to find Samba share paths on TrueNAS Scale

echo "Finding Samba share paths..."
echo ""

# Method 1: Query Samba shares via API
echo "=== Samba Shares (via API) ==="
midclt call smb.shares.query 2>/dev/null | python3 -m json.tool 2>/dev/null | grep -E "(name|path)" | head -20 || {
    echo "Could not query via API, trying alternative method..."
}

echo ""
echo "=== All Datasets (check for media-related) ==="
zfs list | grep -E "(NAME|media|shared|tv|video)" | head -20

echo ""
echo "=== Directories in /mnt/blackhole ==="
ls -la /mnt/blackhole/ 2>/dev/null | head -20

echo ""
echo "To find your media share:"
echo "1. Check the 'path' field from Samba shares above"
echo "2. Or look for media-related datasets"
echo "3. The path format will be: /mnt/blackhole/DATASET_NAME"

