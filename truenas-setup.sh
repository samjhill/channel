#!/bin/bash
# TrueNAS Scale Setup Script
# Run this script on your TrueNAS Scale system to prepare for deployment

set -euo pipefail

echo "========================================="
echo "TV Channel - TrueNAS Scale Setup"
echo "========================================="
echo ""

# Configuration
POOL_NAME="${POOL_NAME:-tank}"
APP_NAME="tvchannel"
MEDIA_DATASET="${MEDIA_DATASET:-media/tv}"
APP_DATASET="apps/${APP_NAME}"

# Detect pool name if not set
if [ "${POOL_NAME}" = "tank" ] && [ ! -d "/mnt/tank" ]; then
    # Try to detect pool from /mnt
    DETECTED_POOL=$(ls -d /mnt/*/ 2>/dev/null | grep -v "/mnt/apps$" | head -1 | sed 's|/mnt/||' | sed 's|/$||')
    if [ -n "${DETECTED_POOL}" ]; then
        echo "Detected pool: ${DETECTED_POOL}"
        POOL_NAME="${DETECTED_POOL}"
    fi
fi

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${YELLOW}Configuration:${NC}"
echo "  Pool Name: ${POOL_NAME}"
echo "  Media Dataset: ${POOL_NAME}/${MEDIA_DATASET}"
echo "  App Dataset: ${POOL_NAME}/${APP_DATASET}"
echo ""
echo -e "${YELLOW}This script will:${NC}"
echo "1. Create datasets for TV Channel application"
echo "2. Set up directory structure"
echo "3. Set appropriate permissions"
echo ""
echo -e "${YELLOW}Note:${NC} If your media is already on a Samba share, you can skip"
echo "      creating the media dataset. Just note the path for docker-compose.yml"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Warn if trying to use system directory
if [ "${POOL_NAME}" = "apps" ]; then
    echo -e "${RED}WARNING: 'apps' is a system directory!${NC}"
    echo "Please set POOL_NAME to your actual pool (e.g., blackhole, tank)"
    echo "Example: POOL_NAME=blackhole $0"
    exit 1
fi

# Create datasets
echo -e "\n${GREEN}Creating datasets...${NC}"

# Media dataset (if it doesn't exist)
if ! zfs list "${POOL_NAME}/${MEDIA_DATASET}" >/dev/null 2>&1; then
    echo "Creating media dataset: ${POOL_NAME}/${MEDIA_DATASET}"
    zfs create -p "${POOL_NAME}/${MEDIA_DATASET}"
else
    echo "Media dataset already exists: ${POOL_NAME}/${MEDIA_DATASET}"
fi

# Application datasets
for subdir in assets config hls; do
    dataset="${POOL_NAME}/${APP_DATASET}/${subdir}"
    if ! zfs list "$dataset" >/dev/null 2>&1; then
        echo "Creating dataset: $dataset"
        zfs create -p "$dataset"
    else
        echo "Dataset already exists: $dataset"
    fi
done

# Set permissions
echo -e "\n${GREEN}Setting permissions...${NC}"

# Media directory - readable by all
chmod -R 755 "/mnt/${POOL_NAME}/${MEDIA_DATASET}" || true

# Application directories - writable
chmod -R 755 "/mnt/${POOL_NAME}/${APP_DATASET}" || true
chmod -R 777 "/mnt/${POOL_NAME}/${APP_DATASET}/hls" || true

# Create initial config directory structure
echo -e "\n${GREEN}Setting up configuration...${NC}"

CONFIG_DIR="/mnt/${POOL_NAME}/${APP_DATASET}/config"
if [ ! -f "${CONFIG_DIR}/channel_settings.json" ]; then
    echo "Creating default channel_settings.json..."
    mkdir -p "${CONFIG_DIR}"
    cat > "${CONFIG_DIR}/channel_settings.json" << 'EOF'
{
  "channels": [
    {
      "id": "main",
      "label": "Main Channel",
      "media_root": "/media/tvchannel"
    }
  ]
}
EOF
fi

# Create assets directory structure
ASSETS_DIR="/mnt/${POOL_NAME}/${APP_DATASET}/assets"
mkdir -p "${ASSETS_DIR}/bumpers" || true
mkdir -p "${ASSETS_DIR}/branding" || true
mkdir -p "${ASSETS_DIR}/music" || true

echo -e "\n${GREEN}Setup complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Place your media files in: /mnt/${POOL_NAME}/${MEDIA_DATASET}/"
echo "2. Update docker-compose.truenas.yml with your paths"
echo "3. Deploy using TrueNAS Apps or docker-compose"
echo ""
echo "Paths configured:"
echo "  Media: /mnt/${POOL_NAME}/${MEDIA_DATASET}"
echo "  Assets: /mnt/${POOL_NAME}/${APP_DATASET}/assets"
echo "  Config: /mnt/${POOL_NAME}/${APP_DATASET}/config"
echo "  HLS: /mnt/${POOL_NAME}/${APP_DATASET}/hls"
echo ""

