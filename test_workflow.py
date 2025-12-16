#!/usr/bin/env python3
"""Test script to monitor and verify episode -> bumper block -> episode workflow."""

import sys
import time
import json
from pathlib import Path

sys.path.insert(0, 'server')

from stream import load_playlist, load_playhead_state, is_episode_entry, is_bumper_block
from bumper_block import get_generator

def check_pregen_status():
    """Check pre-generation status."""
    gen = get_generator()
    thread_alive = gen._pregen_thread.is_alive() if gen._pregen_thread else False
    queue_size = len(gen._pregen_queue)
    cache_size = len(gen._pregenerated_blocks)
    blocks_by_episode = len(gen._blocks_by_episode)
    
    print(f"\n=== Pre-generation Status ===")
    print(f"Thread alive: {thread_alive}")
    print(f"Queue size: {queue_size}")
    print(f"Cache size: {cache_size}")
    print(f"Blocks by episode: {blocks_by_episode}")
    
    if gen._pregenerated_blocks:
        print("\nCached blocks:")
        for i, (hash_key, block) in enumerate(list(gen._pregenerated_blocks.items())[:5]):
            ep_name = Path(block.episode_path).name if block.episode_path else "unknown"
            print(f"  {hash_key[:8]}: {len(block.bumpers) if block.bumpers else 0} bumpers, episode={ep_name}")
    
    if gen._pregen_queue:
        print("\nQueued blocks:")
        for i, spec in enumerate(gen._pregen_queue[:3]):
            ep_name = Path(spec.get('episode_path', '')).name if spec.get('episode_path') else 'unknown'
            print(f"  {i+1}: episode={ep_name}, up_next={Path(spec.get('up_next_bumper', '')).name if spec.get('up_next_bumper') else 'None'}")

def check_playhead():
    """Check current playhead state."""
    state = load_playhead_state()
    if state:
        print(f"\n=== Playhead State ===")
        print(f"Current path: {Path(state.get('current_path', '')).name}")
        print(f"Current index: {state.get('current_index', -1)}")
        print(f"Entry type: {state.get('entry_type', 'unknown')}")
        print(f"Updated at: {time.ctime(state.get('updated_at', 0))}")
    else:
        print("\n=== Playhead State ===")
        print("No playhead state found")

def check_playlist_structure():
    """Check playlist structure around current position."""
    files, mtime = load_playlist()
    state = load_playhead_state()
    
    if not state:
        return
    
    current_idx = state.get('current_index', 0)
    
    print(f"\n=== Playlist Structure (around index {current_idx}) ===")
    start = max(0, current_idx - 2)
    end = min(len(files), current_idx + 5)
    
    for i in range(start, end):
        marker = " <-- CURRENT" if i == current_idx else ""
        entry = files[i]
        if is_episode_entry(entry):
            print(f"  {i}: EPISODE - {Path(entry).name}{marker}")
        elif is_bumper_block(entry):
            print(f"  {i}: BUMPER_BLOCK{marker}")
        else:
            print(f"  {i}: {entry[:60]}{marker}")

def main():
    """Main monitoring loop."""
    print("=" * 60)
    print("Episode -> Bumper Block -> Episode Workflow Monitor")
    print("=" * 60)
    
    iteration = 0
    while True:
        iteration += 1
        print(f"\n{'='*60}")
        print(f"Iteration {iteration} - {time.strftime('%H:%M:%S')}")
        print(f"{'='*60}")
        
        check_pregen_status()
        check_playhead()
        check_playlist_structure()
        
        print(f"\nWaiting 10 seconds... (Ctrl+C to stop)")
        try:
            time.sleep(10)
        except KeyboardInterrupt:
            print("\n\nStopped monitoring.")
            break

if __name__ == "__main__":
    main()





