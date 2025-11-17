"""
Bumper block system: Groups bumpers together with shared background music.
Pre-generates blocks while episodes are playing for instant playback.
"""

from __future__ import annotations

import os
import random
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging

LOGGER = logging.getLogger(__name__)

# Bumper block marker in playlist
BUMPER_BLOCK_MARKER = "BUMPER_BLOCK"

# Directory for pre-generated bumper blocks
BLOCKS_DIR = os.path.join(os.environ.get("HBN_BUMPERS_ROOT", "/media/tvchannel/bumpers"), "blocks")


@dataclass
class BumperBlock:
    """Represents a block of bumpers with shared music."""
    bumpers: List[str]  # List of bumper file paths
    music_track: Optional[str]  # Path to the shared music track
    block_id: str  # Unique identifier for this block


class BumperBlockGenerator:
    """Generates bumper blocks with shared music and manages pre-generation."""
    
    def __init__(self):
        self._pregen_queue: List[Dict[str, Any]] = []
        self._pregen_lock = threading.Lock()
        self._pregen_thread: Optional[threading.Thread] = None
        self._stop_pregen = threading.Event()
        self._blocks_dir = Path(BLOCKS_DIR)
        self._blocks_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_block(
        self,
        up_next_bumper: Optional[str] = None,
        sassy_card: Optional[str] = None,
        network_bumper: Optional[str] = None,
        weather_bumper: Optional[str] = None,
        music_track: Optional[str] = None,
    ) -> Optional[BumperBlock]:
        """
        Generate a bumper block with the specified bumpers and shared music.
        
        Args:
            up_next_bumper: Path to Up Next bumper (if any)
            sassy_card: Path to sassy card (if any)
            network_bumper: Path to network bumper (if any)
            weather_bumper: Path to weather bumper (if any)
            music_track: Path to music track to use (if None, picks randomly)
        
        Returns:
            BumperBlock with all bumpers having the shared music, or None if failed
        """
        # Collect all bumpers (auto-draw if not provided)
        bumpers = []
        
        # Auto-draw sassy card if not provided
        if sassy_card is None:
            try:
                from server.generate_playlist import SASSY_CARDS
                sassy_card = SASSY_CARDS.draw_card()
            except Exception:
                pass
        
        # Auto-draw network bumper if not provided
        if network_bumper is None:
            try:
                from server.generate_playlist import NETWORK_BUMPERS
                network_bumper = NETWORK_BUMPERS.draw_bumper()
            except Exception:
                pass
        
        # Handle weather bumper marker
        if weather_bumper == "WEATHER_BUMPER":
            try:
                from server.stream import _render_weather_bumper_jit
                weather_bumper = _render_weather_bumper_jit()
            except Exception:
                weather_bumper = None
        
        # Collect all valid bumpers
        if up_next_bumper and os.path.exists(up_next_bumper):
            bumpers.append(up_next_bumper)
        if sassy_card and os.path.exists(sassy_card):
            bumpers.append(sassy_card)
        if network_bumper and os.path.exists(network_bumper):
            bumpers.append(network_bumper)
        if weather_bumper and os.path.exists(weather_bumper):
            bumpers.append(weather_bumper)
        
        if not bumpers:
            return None
        
        # Pick music track if not provided
        if not music_track:
            music_track = self._pick_music_track()
            if not music_track:
                LOGGER.warning("No music tracks available, generating block without music")
        
        # Generate block ID
        block_id = f"block_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
        
        # Add music to each bumper in the block
        block_bumpers = []
        for bumper_path in bumpers:
            if not bumper_path or not os.path.exists(bumper_path):
                continue
            
            # Create output path for bumper with music
            bumper_name = Path(bumper_path).stem
            output_path = self._blocks_dir / f"{block_id}_{bumper_name}.mp4"
            
            try:
                if music_track:
                    self._add_music_to_bumper(bumper_path, str(output_path), music_track)
                else:
                    # No music, just copy
                    import shutil
                    shutil.copy2(bumper_path, output_path)
                
                if os.path.exists(output_path):
                    block_bumpers.append(str(output_path))
            except Exception as e:
                LOGGER.error(f"Failed to add music to bumper {bumper_path}: {e}")
                # Fallback: use original bumper
                if os.path.exists(bumper_path):
                    block_bumpers.append(bumper_path)
        
        if not block_bumpers:
            return None
        
        return BumperBlock(
            bumpers=block_bumpers,
            music_track=music_track,
            block_id=block_id
        )
    
    def _pick_music_track(self) -> Optional[str]:
        """Pick a random music track from assets/music/."""
        try:
            from scripts.music.add_music_to_bumper import resolve_music_dir, list_music_files
            
            music_dir = resolve_music_dir()
            tracks = list_music_files(music_dir)
            if tracks:
                return str(random.choice(tracks))
        except Exception as e:
            LOGGER.error(f"Failed to pick music track: {e}")
        return None
    
    def _add_music_to_bumper(
        self,
        bumper_path: str,
        output_path: str,
        music_track: str,
        music_volume: float = 0.2,
    ) -> None:
        """Add music to a bumper using a specific track."""
        try:
            from scripts.music.add_music_to_bumper import add_music_to_bumper
            add_music_to_bumper(bumper_path, output_path, music_track, music_volume)
        except Exception as e:
            LOGGER.error(f"Failed to add music to bumper: {e}")
            raise
    
    def queue_pregen(self, block_spec: Dict[str, Any]) -> None:
        """Queue a bumper block for pre-generation."""
        with self._pregen_lock:
            self._pregen_queue.append(block_spec)
    
    def start_pregen_thread(self) -> None:
        """Start the pre-generation thread."""
        if self._pregen_thread and self._pregen_thread.is_alive():
            return
        
        self._stop_pregen.clear()
        self._pregen_thread = threading.Thread(
            target=self._pregen_worker,
            daemon=True,
            name="BumperBlockPregen"
        )
        self._pregen_thread.start()
        LOGGER.info("Started bumper block pre-generation thread")
    
    def stop_pregen_thread(self) -> None:
        """Stop the pre-generation thread."""
        self._stop_pregen.set()
        if self._pregen_thread:
            self._pregen_thread.join(timeout=5.0)
    
    def _pregen_worker(self) -> None:
        """Worker thread that pre-generates bumper blocks."""
        while not self._stop_pregen.is_set():
            block_spec = None
            with self._pregen_lock:
                if self._pregen_queue:
                    block_spec = self._pregen_queue.pop(0)
            
            if block_spec:
                try:
                    self.generate_block(**block_spec)
                    LOGGER.debug(f"Pre-generated bumper block: {block_spec.get('block_id', 'unknown')}")
                except Exception as e:
                    LOGGER.error(f"Failed to pre-generate bumper block: {e}")
            else:
                # No work, sleep briefly
                time.sleep(0.5)


# Global instance
_generator: Optional[BumperBlockGenerator] = None


def get_generator() -> BumperBlockGenerator:
    """Get the global bumper block generator instance."""
    global _generator
    if _generator is None:
        _generator = BumperBlockGenerator()
    return _generator

