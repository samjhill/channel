#!/bin/bash
# Fix TV directory permissions to match movies directory

TV_DIR="/mnt/blackhole/media/tv"
MOVIES_DIR="/mnt/blackhole/media/movies"

echo "=== Current state ==="
ls -ld "$TV_DIR"
ls -ld "$MOVIES_DIR"
echo ""

echo "=== Checking what's in movies directory ==="
ls -1 "$MOVIES_DIR" | head -10
echo ""

echo "=== Searching for The Office in movies ==="
find "$MOVIES_DIR" -maxdepth 1 -type d -iname "*office*" 2>/dev/null
echo ""

echo "=== Fixing TV directory permissions to match movies ==="
# Set ownership to match movies (sam:root)
chown sam:root "$TV_DIR"
chmod 770 "$TV_DIR"  # drwxrwx---

echo "=== Updated permissions ==="
ls -ld "$TV_DIR"
echo ""

echo "=== Testing write access ==="
if touch "$TV_DIR/.test_write" 2>/dev/null; then
    echo "✓ Write access works!"
    rm -f "$TV_DIR/.test_write"
else
    echo "✗ Write access still blocked"
    echo "You may need to run: sudo chown sam:root $TV_DIR"
fi

echo ""
echo "=== Note ==="
echo "If your TV shows are actually in /mnt/blackhole/media/movies,"
echo "we should update the Docker volume mount to point there instead."

