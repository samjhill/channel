#!/bin/bash
# Fix permissions on media directories

MEDIA_DIR="/mnt/blackhole/media"
TV_DIR="/mnt/blackhole/media/tv"

echo "=== Current permissions ==="
echo "Parent directory:"
ls -ld "$MEDIA_DIR"
echo ""
echo "TV directory:"
ls -ld "$TV_DIR"
echo ""

echo "=== Checking ZFS dataset properties ==="
zfs get all blackhole/media/tv 2>/dev/null | grep -E "(acltype|aclmode|permissions|canmount)"
echo ""

echo "=== Checking ACLs ==="
getfacl "$TV_DIR" 2>/dev/null || echo "getfacl not available or no ACLs set"
echo ""

echo "=== Fixing permissions ==="
# Set ownership
chown -R root:root "$TV_DIR" 2>/dev/null
chmod 755 "$TV_DIR" 2>/dev/null

# Also fix parent
chown root:root "$MEDIA_DIR" 2>/dev/null
chmod 755 "$MEDIA_DIR" 2>/dev/null

echo "=== Updated permissions ==="
ls -ld "$MEDIA_DIR"
ls -ld "$TV_DIR"
echo ""

echo "=== Testing write access ==="
if touch "$TV_DIR/.test_write" 2>/dev/null; then
    echo "✓ Write access works!"
    rm -f "$TV_DIR/.test_write"
else
    echo "✗ Write access still blocked"
    echo ""
    echo "This might be a ZFS dataset ACL issue. Try:"
    echo "  zfs set acltype=posixacl blackhole/media/tv"
    echo "  zfs set aclmode=passthrough blackhole/media/tv"
    echo "  chmod 755 $TV_DIR"
fi

