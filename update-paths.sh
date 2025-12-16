#!/bin/bash
# Quick script to update docker-compose paths for your app directory name

set -euo pipefail

APP_DIR="${1:-channel}"  # Default to 'channel'
POOL_NAME="${POOL_NAME:-blackhole}"

COMPOSE_FILE="docker-compose.truenas.yml"

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "Error: $COMPOSE_FILE not found"
    exit 1
fi

echo "Updating docker-compose.truenas.yml for app directory: $APP_DIR"
echo "Pool: $POOL_NAME"

# Update paths in docker-compose file
sed -i.bak \
    -e "s|/mnt/blackhole/apps/tvchannel|/mnt/${POOL_NAME}/apps/${APP_DIR}|g" \
    -e "s|/mnt/tank/apps/tvchannel|/mnt/${POOL_NAME}/apps/${APP_DIR}|g" \
    "$COMPOSE_FILE"

echo "Updated! Backup saved as ${COMPOSE_FILE}.bak"
echo ""
echo "Updated paths:"
grep -E "(volumes:|/mnt/)" "$COMPOSE_FILE" | head -5

