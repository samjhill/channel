#!/bin/bash
# Restart Samba and verify TV shows are accessible

echo "=== Restarting Samba Service ==="
echo ""

echo "1. Checking current Samba status..."
systemctl status smbd --no-pager -l 2>/dev/null | head -5 || service smbd status 2>/dev/null | head -5
echo ""

echo "2. Stopping Samba (if running)..."
systemctl stop smbd 2>/dev/null || service smbd stop 2>/dev/null
sleep 2
echo "   ✓ Stopped"
echo ""

echo "3. Starting Samba..."
systemctl start smbd 2>/dev/null || service smbd start 2>/dev/null

if [ $? -eq 0 ]; then
    echo "   ✓ Samba started successfully"
else
    echo "   ✗ Failed to start Samba"
    echo "   Try manually: systemctl start smbd"
    exit 1
fi

echo ""
echo "4. Waiting for Samba to initialize..."
sleep 3

echo ""
echo "5. Checking Samba status..."
systemctl status smbd --no-pager -l 2>/dev/null | head -10 || service smbd status 2>/dev/null | head -10
echo ""

echo "6. Verifying TV shows are accessible..."
if [ -d "/mnt/blackhole/media/tv" ] && [ "$(ls -A /mnt/blackhole/media/tv 2>/dev/null)" ]; then
    SHOW_COUNT=$(find /mnt/blackhole/media/tv -maxdepth 1 -type d 2>/dev/null | wc -l)
    echo "   ✓ TV shows directory accessible"
    echo "   Shows found: $SHOW_COUNT directories"
    echo ""
    echo "   Sample shows:"
    ls -1 /mnt/blackhole/media/tv | head -5
else
    echo "   ⚠️  TV shows directory not found or empty"
fi

echo ""
echo "7. Checking Samba shares..."
smbstatus 2>/dev/null | head -20 || echo "   smbstatus not available or no active connections"
echo ""

echo "=== Samba Restarted Successfully! ==="
echo ""
echo "Your TV shows are accessible at:"
echo "  /mnt/blackhole/media/tv"
echo ""
echo "To access via Samba from your Mac/PC:"
echo "  1. Open Finder (Mac) or File Explorer (Windows)"
echo "  2. Connect to server: smb://YOUR_TRUENAS_IP"
echo "  3. Navigate to your media share"
echo ""
echo "To check what shares are configured:"
echo "  - TrueNAS UI: Shares → SMB Shares"
echo "  - Or: smbclient -L localhost -N"
echo ""
echo "If you need to create/update a Samba share for TV shows:"
echo "  1. Go to TrueNAS UI → Shares → SMB Shares"
echo "  2. Add or edit a share pointing to: /mnt/blackhole/media/tv"
echo "  3. Set appropriate permissions"
echo ""
echo "Current Samba service status:"
systemctl is-active smbd 2>/dev/null && echo "  ✓ Active" || echo "  ✗ Inactive"

