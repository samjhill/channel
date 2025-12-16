#!/bin/bash
# Pre-rebuild safety checks

echo "=== Pre-Rebuild Safety Checks ==="
echo ""

ERRORS=0

echo "1. Checking Docker configuration..."
if [ -f "docker-compose.truenas.yml" ]; then
    echo "   ✓ docker-compose.truenas.yml exists"
    
    # Check media mount is read-only
    if grep -q "/mnt/blackhole/media/tv:/media/tvchannel:ro" docker-compose.truenas.yml; then
        echo "   ✓ Media mount is read-only (:ro flag present)"
    else
        echo "   ✗ Media mount missing or not read-only!"
        ERRORS=$((ERRORS + 1))
    fi
    
    # Check HLS mount exists
    if grep -q "/mnt/blackhole/apps/tvchannel/hls:/app/hls" docker-compose.truenas.yml; then
        echo "   ✓ HLS mount configured"
    else
        echo "   ✗ HLS mount missing!"
        ERRORS=$((ERRORS + 1))
    fi
    
    # Check config mount exists
    if grep -q "/mnt/blackhole/apps/tvchannel/config:/app/config" docker-compose.truenas.yml; then
        echo "   ✓ Config mount configured"
    else
        echo "   ✗ Config mount missing!"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "   ✗ docker-compose.truenas.yml not found!"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "2. Checking media path exists..."
if [ -d "/mnt/blackhole/media/tv" ]; then
    SHOW_COUNT=$(find /mnt/blackhole/media/tv -maxdepth 1 -type d 2>/dev/null | wc -l)
    if [ "$SHOW_COUNT" -gt 1 ]; then
        echo "   ✓ Media path exists with $SHOW_COUNT directories"
    else
        echo "   ⚠️  Media path exists but appears empty"
    fi
else
    echo "   ✗ Media path /mnt/blackhole/media/tv does not exist!"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "3. Checking application directories..."
for dir in "/mnt/blackhole/apps/tvchannel/hls" "/mnt/blackhole/apps/tvchannel/config" "/mnt/blackhole/apps/tvchannel/assets"; do
    if [ -d "$dir" ]; then
        echo "   ✓ $dir exists"
    else
        echo "   ⚠️  $dir does not exist (will be created)"
        mkdir -p "$dir" 2>/dev/null && echo "      Created" || echo "      Failed to create"
    fi
done

echo ""
echo "4. Checking bumper blocks fix..."
if grep -q "/app/hls/blocks" server/bumper_block.py; then
    echo "   ✓ Bumper blocks will write to container-local path"
else
    echo "   ✗ Bumper blocks path not fixed!"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "5. Checking if container is running..."
if docker ps | grep -q tvchannel; then
    echo "   ⚠️  Container is currently running"
    echo "      It will be stopped during rebuild"
else
    echo "   ✓ Container is not running (safe to rebuild)"
fi

echo ""
echo "=== Summary ==="
if [ $ERRORS -eq 0 ]; then
    echo "✅ All checks passed! Safe to rebuild."
    echo ""
    echo "To rebuild and restart:"
    echo "  docker build -t tvchannel:latest -f server/Dockerfile ."
    echo "  docker-compose -f docker-compose.truenas.yml up -d"
    exit 0
else
    echo "❌ Found $ERRORS error(s). Please fix before rebuilding."
    exit 1
fi

