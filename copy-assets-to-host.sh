#!/bin/bash
# Copy assets from repo to host assets directory

echo "=== Copying Assets to Host Directory ==="
echo ""

ASSETS_HOST="/mnt/blackhole/apps/tvchannel/assets"
ASSETS_REPO="assets"

if [ ! -d "$ASSETS_REPO" ]; then
    echo "Error: assets directory not found in repo"
    exit 1
fi

echo "1. Creating assets directory on host..."
mkdir -p "$ASSETS_HOST/branding"
mkdir -p "$ASSETS_HOST/bumpers"
mkdir -p "$ASSETS_HOST/music"

echo ""
echo "2. Copying branding assets..."
if [ -f "$ASSETS_REPO/branding/hbn_logo_bug.png" ]; then
    cp "$ASSETS_REPO/branding/hbn_logo_bug.png" "$ASSETS_HOST/branding/" && echo "   ✓ Copied logo file"
else
    echo "   ✗ Logo file not found in repo!"
fi

if [ -f "$ASSETS_REPO/branding/hbn_logo_bug.svg" ]; then
    cp "$ASSETS_REPO/branding/hbn_logo_bug.svg" "$ASSETS_HOST/branding/" && echo "   ✓ Copied logo SVG"
fi

echo ""
echo "3. Verifying logo file exists..."
if [ -f "$ASSETS_HOST/branding/hbn_logo_bug.png" ]; then
    echo "   ✓ Logo file is now in host directory"
    ls -lh "$ASSETS_HOST/branding/hbn_logo_bug.png"
else
    echo "   ✗ Logo file still missing!"
fi

echo ""
echo "=== Done ==="
echo "Restart container to pick up the logo file:"
echo "  docker compose -f docker-compose.truenas.yml restart"

