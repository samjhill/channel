#!/bin/bash
# Check container logs for bumper preview errors

echo "=== Checking Bumper Preview Errors ==="
echo ""

echo "1. Recent preview-related errors from container logs:"
docker logs tvchannel 2>&1 | grep -i "preview\|bumper.*preview" | tail -30
echo ""

echo "2. Recent API errors:"
docker logs tvchannel 2>&1 | grep -i "error\|exception\|failed" | tail -20
echo ""

echo "3. Checking if bumper blocks exist:"
docker exec tvchannel python3 -c "
import sys
sys.path.insert(0, '/app')
from server.bumper_block import get_generator
gen = get_generator()
block = gen.peek_next_pregenerated_block()
if block:
    print(f'✓ Found pre-generated block with {len(block.bumpers)} bumpers')
    print(f'  Block ID: {block.block_id}')
    print(f'  Episode: {block.episode_path}')
    print(f'  Bumpers:')
    for b in block.bumpers:
        print(f'    - {b}')
else:
    print('✗ No pre-generated blocks found')
" 2>&1
echo ""

echo "4. Checking if playlist has entries:"
docker exec tvchannel python3 -c "
import sys
sys.path.insert(0, '/app')
from server.playlist_service import load_playlist_entries
try:
    entries, mtime = load_playlist_entries()
    print(f'✓ Playlist has {len(entries)} entries')
    episode_count = sum(1 for e in entries if e.strip() and not e.strip().startswith('#'))
    print(f'  Episodes: {episode_count}')
except Exception as e:
    print(f'✗ Failed to load playlist: {e}')
" 2>&1
echo ""

echo "5. Testing preview endpoint directly:"
curl -s "http://localhost:8000/api/bumper-preview/next?ts=$(date +%s)" | head -c 500
echo ""
echo ""

echo "=== Done ==="

