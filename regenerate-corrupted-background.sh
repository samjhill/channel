#!/bin/bash
# Manually regenerate corrupted background 1 by deleting it and forcing regeneration

echo "Deleting corrupted background 1..."
docker exec tvchannel rm -f /app/assets/bumpers/up_next/backgrounds/bg_01.mp4

echo "Regenerating background 1..."
docker exec tvchannel python3 -c "
import sys
sys.path.insert(0, '/app')
from scripts.bumpers.generate_up_next_backgrounds import generate_background_video
from pathlib import Path
output_path = Path('/app/assets/bumpers/up_next/backgrounds/bg_01.mp4')
if generate_background_video(1, output_path):
    print('✓ Successfully regenerated background 1')
else:
    print('✗ Failed to regenerate background 1')
    sys.exit(1)
"

echo ""
echo "Done! Check the output above to verify regeneration was successful."

