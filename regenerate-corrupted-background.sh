#!/bin/bash
# Manually regenerate corrupted background 1

echo "Regenerating corrupted background 1..."
docker exec tvchannel python3 /app/scripts/bumpers/generate_up_next_backgrounds.py --background-id 1 --force

echo ""
echo "Done! Check logs to verify regeneration was successful."

