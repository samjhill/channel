#!/bin/bash
# Check what's referencing the busy dataset

echo "=== Checking Dataset References ==="
echo ""

echo "1. Checking Samba configuration..."
if [ -f "/etc/smb4.conf" ]; then
    echo "   Checking for references to media/tv:"
    grep -i "media/tv\|media.*tv" /etc/smb4.conf | grep -v "^#" || echo "   No references found in smb4.conf"
else
    echo "   smb4.conf not found (might be in TrueNAS config)"
fi
echo ""

echo "2. Checking Docker volumes..."
docker volume ls 2>/dev/null | grep -i "media\|tv" || echo "   No Docker volumes found"
echo ""

echo "3. Checking Docker containers..."
docker ps -a 2>/dev/null | grep -i "tvchannel\|media" || echo "   No Docker containers found"
echo ""

echo "4. Checking if dataset has any properties that might lock it..."
zfs get all blackhole/media/tv 2>/dev/null | grep -E "(share|mount|canmount|busy)" || echo "   No special properties found"
echo ""

echo "5. Checking mount points..."
mount | grep "blackhole/media/tv" || echo "   Not currently mounted"
echo ""

echo "=== Current Status ==="
echo "Your shows ARE visible at /mnt/blackhole/media/tv"
echo "The dataset is unmounted (mount status: no)"
echo ""
echo "Since your shows are already accessible, you have options:"
echo ""
echo "Option 1: Leave it as-is (RECOMMENDED)"
echo "  - Shows are accessible"
echo "  - Dataset is unmounted, so it's not interfering"
echo "  - Just update Docker to use /mnt/blackhole/media/tv"
echo ""
echo "Option 2: Check TrueNAS Samba Shares UI"
echo "  - Go to: Shares → SMB Shares"
echo "  - Look for any share pointing to /mnt/blackhole/media/tv"
echo "  - Edit or delete that share"
echo "  - Then try: zfs destroy blackhole/media/tv"
echo ""
echo "Option 3: Reboot (will release all locks)"
echo "  - After reboot: zfs destroy blackhole/media/tv"
echo ""
echo "Since shows are visible, Option 1 is safest!"

