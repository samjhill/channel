#!/bin/bash
# Verify media mount is correct and read-only

echo "=== Verifying Media Mount Configuration ==="
echo ""

ERRORS=0

echo "1. Checking docker-compose.truenas.yml..."
if [ -f "docker-compose.truenas.yml" ]; then
    echo "   ✓ File exists"
    
    # Check for read-only flag
    if grep -q "/mnt/blackhole/media/tv:/media/tvchannel:ro" docker-compose.truenas.yml; then
        echo "   ✓ Media mount is READ-ONLY (:ro flag present)"
    else
        echo "   ✗ CRITICAL: Media mount is NOT read-only!"
        echo "      This could allow the app to modify/delete your TV shows!"
        ERRORS=$((ERRORS + 1))
    fi
    
    # Check path is correct
    if grep -q "/mnt/blackhole/media/tv" docker-compose.truenas.yml; then
        echo "   ✓ Media path is correct: /mnt/blackhole/media/tv"
    else
        echo "   ✗ Media path is incorrect!"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "   ✗ docker-compose.truenas.yml not found!"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "2. Checking if media directory exists on host..."
if [ -d "/mnt/blackhole/media/tv" ]; then
    SHOW_COUNT=$(find /mnt/blackhole/media/tv -maxdepth 1 -type d 2>/dev/null | wc -l)
    if [ "$SHOW_COUNT" -gt 1 ]; then
        echo "   ✓ Media directory exists with $SHOW_COUNT directories"
        echo "   Sample shows:"
        ls -1 /mnt/blackhole/media/tv | head -5 | sed 's/^/      /'
    else
        echo "   ⚠️  Media directory exists but appears empty"
    fi
else
    echo "   ✗ Media directory /mnt/blackhole/media/tv does not exist!"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "3. Checking container mount (if running)..."
if docker ps | grep -q tvchannel; then
    echo "   Container is running, checking mount..."
    
    # Check if mount is read-only in container
    MOUNT_INFO=$(docker inspect tvchannel 2>/dev/null | grep -A 10 "Mounts" | grep -A 5 "media/tvchannel")
    if echo "$MOUNT_INFO" | grep -q '"Mode": "ro"'; then
        echo "   ✓ Container mount is READ-ONLY"
    else
        echo "   ✗ CRITICAL: Container mount is NOT read-only!"
        ERRORS=$((ERRORS + 1))
    fi
    
    # Test if we can read from it
    if docker exec tvchannel test -d /media/tvchannel 2>/dev/null; then
        CONTAINER_SHOWS=$(docker exec tvchannel ls -1 /media/tvchannel 2>/dev/null | wc -l)
        echo "   ✓ Container can access media directory ($CONTAINER_SHOWS items)"
    else
        echo "   ✗ Container cannot access /media/tvchannel"
        ERRORS=$((ERRORS + 1))
    fi
    
    # Test if we can write to it (should fail)
    if docker exec tvchannel touch /media/tvchannel/.test_write 2>/dev/null; then
        echo "   ✗ CRITICAL: Container CAN write to media mount (should be read-only)!"
        docker exec tvchannel rm -f /media/tvchannel/.test_write 2>/dev/null
        ERRORS=$((ERRORS + 1))
    else
        echo "   ✓ Container CANNOT write to media mount (correct - read-only)"
    fi
else
    echo "   Container is not running (will check after start)"
fi

echo ""
echo "4. Verifying application code doesn't write to media..."
# Check that bumper blocks don't write to media mount
if grep -q "/app/hls/blocks" server/bumper_block.py; then
    echo "   ✓ Bumper blocks write to container-local path (/app/hls/blocks)"
else
    echo "   ⚠️  Bumper blocks path needs verification"
fi

# Check that no code tries to write to /media/tvchannel (ignore comments)
WRITE_PATTERNS=$(grep -r "open.*/media/tvchannel.*w\|write.*/media/tvchannel\|mkdir.*/media/tvchannel" server/ 2>/dev/null | grep -v ".pyc" | grep -v "__pycache__" | grep -v "^[^:]*:#" | grep -v "Never writes\|read-only\|#.*write")
if [ -n "$WRITE_PATTERNS" ]; then
    echo "   ✗ WARNING: Found code that might write to media mount!"
    echo "$WRITE_PATTERNS" | head -3 | sed 's/^/      /'
    ERRORS=$((ERRORS + 1))
else
    echo "   ✓ No code writes to /media/tvchannel"
fi

echo ""
echo "=== Summary ==="
if [ $ERRORS -eq 0 ]; then
    echo "✅ All checks passed! Media mount is correctly configured as READ-ONLY."
    echo ""
    echo "Your TV shows are protected:"
    echo "  - Mount is read-only (:ro flag)"
    echo "  - Application only reads from /media/tvchannel"
    echo "  - All writes go to container-local paths (/app/hls, /app/config)"
    exit 0
else
    echo "❌ Found $ERRORS critical error(s)!"
    echo ""
    echo "Please fix these issues before starting the container."
    exit 1
fi

