"""
Bumper block system: Groups bumpers together with shared background music.
Pre-generates blocks while episodes are playing for instant playback.
"""

from __future__ import annotations

import os
import random
import threading
import time
import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging

LOGGER = logging.getLogger(__name__)

# Bumper block marker in playlist
BUMPER_BLOCK_MARKER = "BUMPER_BLOCK"

# Directory for pre-generated bumper blocks
BLOCKS_DIR = os.path.join(os.environ.get("HBN_BUMPERS_ROOT", "/media/tvchannel/bumpers"), "blocks")
DEFAULT_BUMPER_DURATION = 6.0


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
        # Cache for pre-generated blocks, keyed by spec hash
        self._pregenerated_blocks: Dict[str, BumperBlock] = {}
    
    def _spec_hash(self, up_next_bumper: Optional[str], sassy_card: Optional[str], 
                   network_bumper: Optional[str], weather_bumper: Optional[str]) -> str:
        """Generate a hash for a block specification."""
        spec_str = f"{up_next_bumper}|{sassy_card}|{network_bumper}|{weather_bumper}"
        return hashlib.md5(spec_str.encode()).hexdigest()
    
    def get_pregenerated_block(
        self,
        up_next_bumper: Optional[str] = None,
        sassy_card: Optional[str] = None,
        network_bumper: Optional[str] = None,
        weather_bumper: Optional[str] = None,
    ) -> Optional[BumperBlock]:
        """Retrieve a pre-generated block matching the spec, if available.
        
        If sassy_card is None, tries to match any block with the same up_next_bumper.
        This allows using pre-generated blocks even if the sassy card was drawn differently.
        """
        # First try exact match
        spec_hash = self._spec_hash(up_next_bumper, sassy_card, network_bumper, weather_bumper)
        with self._pregen_lock:
            if spec_hash in self._pregenerated_blocks:
                block = self._pregenerated_blocks.pop(spec_hash)
                LOGGER.info(f"Retrieved pre-generated bumper block (exact match) {spec_hash}")
                return block
            
            # If sassy_card is None, try to find any block with matching up_next_bumper
            # This allows us to use pre-generated blocks even if sassy card differs
            if sassy_card is None and up_next_bumper:
                # First try matching by hash with None for sassy (in case block was queued that way)
                test_hash = self._spec_hash(up_next_bumper, None, None, weather_bumper if weather_bumper else None)
                if test_hash in self._pregenerated_blocks:
                    block = self._pregenerated_blocks.pop(test_hash)
                    LOGGER.info(f"Retrieved pre-generated bumper block (hash match with None sassy) {test_hash}")
                    return block
                
                # Try with just up_next (no weather)
                test_hash = self._spec_hash(up_next_bumper, None, None, None)
                if test_hash in self._pregenerated_blocks:
                    block = self._pregenerated_blocks.pop(test_hash)
                    LOGGER.info(f"Retrieved pre-generated bumper block (hash match up_next only) {test_hash}")
                    return block
                
                # Iterate through all pre-generated blocks to find one with matching up_next
                # Check the block's actual bumpers list to see if it contains our up_next_bumper
                for cached_hash, cached_block in list(self._pregenerated_blocks.items()):
                    if cached_block and cached_block.bumpers:
                        # Check if this block contains our up_next_bumper
                        # The up_next_bumper should be in the bumpers list (typically 3rd position)
                        if up_next_bumper in cached_block.bumpers:
                            block = self._pregenerated_blocks.pop(cached_hash)
                            LOGGER.info(f"Retrieved pre-generated bumper block (up_next match in bumpers) {cached_hash}")
                            return block
                
                # Last resort: return the first available block (FIFO)
                # This ensures we use pre-generated blocks rather than generating new ones
                if self._pregenerated_blocks:
                    first_hash = next(iter(self._pregenerated_blocks.keys()))
                    block = self._pregenerated_blocks.pop(first_hash)
                    LOGGER.info(f"Retrieved pre-generated bumper block (first available) {first_hash}")
                    return block
        
        return None
    
    def generate_block(
        self,
        up_next_bumper: Optional[str] = None,
        sassy_card: Optional[str] = None,
        network_bumper: Optional[str] = None,
        weather_bumper: Optional[str] = None,
        music_track: Optional[str] = None,
        skip_music: bool = False,
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
        
        sassy_exists = sassy_card and os.path.exists(sassy_card)
        weather_exists = weather_bumper and os.path.exists(weather_bumper)
        up_next_exists = up_next_bumper and os.path.exists(up_next_bumper)
        network_exists = network_bumper and os.path.exists(network_bumper)

        if not (sassy_exists and weather_exists and up_next_exists):
            LOGGER.warning(
                "Incomplete bumper block spec (sassy=%s, weather=%s, up_next=%s) - skipping block",
                bool(sassy_exists),
                bool(weather_exists),
                bool(up_next_exists),
            )
            return None

        # Collect all valid bumpers in the correct order:
        # 1. Sassy card (exactly one)
        # 2. Weather bumper
        # 3. Up next bumper
        # 4. Network bumper (optional, at the end)
        # Ensure we only add each bumper once and in the correct order
        if sassy_exists:
            bumpers.append(sassy_card)
        if weather_exists:
            bumpers.append(weather_bumper)
        if up_next_exists:
            bumpers.append(up_next_bumper)
        if network_exists:
            bumpers.append(network_bumper)
        
        # Sanity check: ensure we don't have duplicate sassy cards
        sassy_count = sum(1 for b in bumpers if b and "/bumpers/sassy/" in b)
        if sassy_count > 1:
            LOGGER.error(f"ERROR: Block has {sassy_count} sassy cards! This should never happen. Bumpers: {bumpers}")
            # Remove duplicate sassy cards, keep only the first one
            seen_sassy = False
            filtered_bumpers = []
            for b in bumpers:
                if b and "/bumpers/sassy/" in b:
                    if not seen_sassy:
                        filtered_bumpers.append(b)
                        seen_sassy = True
                    # Skip duplicate sassy cards
                else:
                    filtered_bumpers.append(b)
            bumpers = filtered_bumpers
            LOGGER.warning(f"Fixed duplicate sassy cards. New bumpers: {bumpers}")
        
        if not bumpers:
            return None
        
        # Pick music track if not provided and not skipping music
        if not skip_music and not music_track:
            music_track = self._pick_music_track()
            if not music_track:
                LOGGER.warning("No music tracks available, generating block without music")
        
        # Generate block ID
        block_id = f"block_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
        
        # Build bumper entries with durations for offset tracking
        bumper_entries = []
        for bumper_path in bumpers:
            if not bumper_path or not os.path.exists(bumper_path):
                continue
            duration = self._probe_bumper_duration(bumper_path) or DEFAULT_BUMPER_DURATION
            bumper_entries.append((bumper_path, duration))
        if not bumper_entries:
            return None
        
        total_duration = sum(duration for _, duration in bumper_entries)
        track_duration = self._probe_audio_duration(music_track) if music_track else None
        needs_loop = (
            not track_duration or track_duration + 0.25 < total_duration
        )
        
        # Add music to each bumper in the block (or use originals if skipping music)
        block_bumpers = []
        cumulative_offset = 0.0
        for bumper_path, duration in bumper_entries:
            if skip_music or not music_track:
                block_bumpers.append(bumper_path)
            else:
                bumper_name = Path(bumper_path).stem
                output_path = self._blocks_dir / f"{block_id}_{bumper_name}.mp4"
                
                try:
                    self._add_music_to_bumper(
                        bumper_path,
                        str(output_path),
                        music_track,
                        music_volume=0.2,
                        start_offset=cumulative_offset,
                        segment_duration=duration,
                        loop_track=needs_loop,
                    )
                    if os.path.exists(output_path):
                        block_bumpers.append(str(output_path))
                    else:
                        # Fallback: use original
                        block_bumpers.append(bumper_path)
                except Exception as e:
                    LOGGER.error(f"Failed to add music to bumper {bumper_path}: {e}")
                    # Fallback: use original bumper
                    if os.path.exists(bumper_path):
                        block_bumpers.append(bumper_path)
            cumulative_offset += duration
        
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
        start_offset: float = 0.0,
        segment_duration: Optional[float] = None,
        loop_track: bool = True,
    ) -> None:
        """Add music to a bumper using a specific track."""
        try:
            from scripts.music.add_music_to_bumper import add_music_to_bumper
            add_music_to_bumper(
                bumper_path,
                output_path,
                music_track,
                music_volume,
                start_offset=start_offset,
                segment_duration=segment_duration,
                loop_track=loop_track,
            )
        except Exception as e:
            LOGGER.error(f"Failed to add music to bumper: {e}")
            raise

    def _probe_bumper_duration(self, bumper_path: str) -> Optional[float]:
        """Get the duration of a bumper video in seconds."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    bumper_path,
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            value = result.stdout.strip()
            return float(value) if value else None
        except Exception:
            return None

    def _probe_audio_duration(self, audio_path: Optional[str]) -> Optional[float]:
        if not audio_path:
            return None
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            value = result.stdout.strip()
            return float(value) if value else None
        except Exception:
            return None
    
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
                    # Generate block with music (for pre-generation)
                    block = self.generate_block(**block_spec, skip_music=False)
                    if block:
                        # Store in cache for later retrieval
                        spec_hash = self._spec_hash(
                            block_spec.get("up_next_bumper"),
                            block_spec.get("sassy_card"),
                            block_spec.get("network_bumper"),
                            block_spec.get("weather_bumper"),
                        )
                        with self._pregen_lock:
                            self._pregenerated_blocks[spec_hash] = block
                        LOGGER.info(f"Pre-generated bumper block {spec_hash} (cache size: {len(self._pregenerated_blocks)})")
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

