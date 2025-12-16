#!/bin/bash
set -euo pipefail

# Cleanup function for graceful shutdown
cleanup() {
    echo "Shutting down gracefully..."
    # Kill any remaining FFmpeg processes
    pkill -9 ffmpeg 2>/dev/null || true
    exit 0
}

trap cleanup SIGTERM SIGINT

# Copy assets from image backup to volume-mounted directory if missing
# The volume mount overrides /app/assets, so we use /app/assets_backup as source
echo "Checking and copying assets from image backup..."
if [ -d "/app/assets_backup" ]; then
    # Copy logo if missing
    if [ ! -f "/app/assets/branding/hbn_logo_bug.png" ] && [ -f "/app/assets_backup/branding/hbn_logo_bug.png" ]; then
        echo "  Copying logo file to assets directory..."
        mkdir -p /app/assets/branding
        cp /app/assets_backup/branding/hbn_logo_bug.png /app/assets/branding/ 2>/dev/null || true
    fi
    
    # Copy up-next backgrounds if missing (ensure all 12 backgrounds are available)
    if [ -d "/app/assets_backup/bumpers/up_next/backgrounds" ]; then
        BACKGROUNDS_DIR="/app/assets/bumpers/up_next/backgrounds"
        BACKUP_DIR="/app/assets_backup/bumpers/up_next/backgrounds"
        
        # Count existing backgrounds
        EXISTING_COUNT=$(ls -1 "$BACKGROUNDS_DIR"/*.mp4 2>/dev/null 2>/dev/null | wc -l || echo "0")
        BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/*.mp4 2>/dev/null | wc -l || echo "0")
        
        echo "  Found $EXISTING_COUNT existing backgrounds, $BACKUP_COUNT available in backup"
        
        # If we don't have all 12 backgrounds, copy from backup
        if [ "$EXISTING_COUNT" -lt 12 ] && [ "$BACKUP_COUNT" -gt 0 ]; then
            echo "  Copying up-next backgrounds from image backup to assets directory..."
            mkdir -p "$BACKGROUNDS_DIR"
            # Copy all backgrounds from backup
            cp "$BACKUP_DIR"/*.mp4 "$BACKGROUNDS_DIR"/ 2>/dev/null || true
            NEW_COUNT=$(ls -1 "$BACKGROUNDS_DIR"/*.mp4 2>/dev/null | wc -l || echo "0")
            echo "  ✓ Copied backgrounds: $NEW_COUNT total backgrounds now available"
        elif [ "$EXISTING_COUNT" -ge 12 ]; then
            echo "  ✓ All 12 backgrounds already present, skipping copy"
        else
            echo "  ⚠ No backgrounds found in backup, will generate on demand"
        fi
    else
        echo "  ⚠ Backup backgrounds directory not found"
    fi
else
    echo "  ⚠ Assets backup directory not found"
fi

# Start nginx first so the HLS endpoint is available immediately
# Ensure our custom config is used and default sites are disabled
rm -f /etc/nginx/sites-enabled/* 2>/dev/null || true
nginx -t && service nginx start || true

# Clean up old HLS segments on startup (in case of previous crash)
echo "Cleaning up old HLS segments..."
python3 -c "
import sys
sys.path.insert(0, '/app')
from server.stream import cleanup_old_hls_segments
cleanup_old_hls_segments(max_age_hours=2.0, max_segments=100)
" || {
    echo "Warning: Failed to cleanup HLS segments, continuing anyway..."
}

# Ensure up-next bumper backgrounds are generated before starting
echo "Checking for up-next bumper backgrounds..."
python3 /app/scripts/bumpers/generate_up_next_backgrounds.py || {
    echo "Warning: Failed to generate backgrounds, continuing anyway..."
}

# Start process monitor which will manage generate_playlist.py and stream.py
# The monitor will automatically restart processes if they crash
python3 /app/process_monitor.py
