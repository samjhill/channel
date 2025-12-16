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
def _resolve_blocks_dir() -> str:
    """Resolve the blocks directory path, handling both Docker and baremetal.
    
    IMPORTANT: In Docker, blocks are written to /app/hls/blocks (container-local, writable).
    Never writes to /media/tvchannel (read-only media mount).
    """
    override = os.environ.get("HBN_BUMPERS_ROOT")
    if override:
        return os.path.join(override, "blocks")
    
    # Check if running in Docker
    if Path("/app").exists():
        # Docker: use HLS directory (container-local, writable)
        # This ensures blocks are written to /app/hls/blocks, not the read-only media mount
        hls_blocks = "/app/hls/blocks"
        return hls_blocks
    
    # Baremetal: use assets directory
    try:
        from server.generate_playlist import ASSETS_ROOT
        return os.path.join(ASSETS_ROOT, "bumpers", "blocks")
    except ImportError:
        # Fallback to relative path
        repo_root = Path(__file__).resolve().parent.parent
        return str(repo_root / "assets" / "bumpers" / "blocks")

BLOCKS_DIR = _resolve_blocks_dir()
DEFAULT_BUMPER_DURATION = 6.0


@dataclass
class BumperBlock:
    """Represents a block of bumpers with shared music."""
    bumpers: List[str]  # List of bumper file paths
    music_track: Optional[str]  # Path to the shared music track
    block_id: str  # Unique identifier for this block
    episode_path: Optional[str] = None  # Episode this block is for (for preview/retrieval)


class BumperBlockGenerator:
    """Generates bumper blocks with shared music and manages pre-generation."""
    
    def __init__(self):
        self._pregen_queue: List[Dict[str, Any]] = []
        self._pregen_lock = threading.Lock()
        self._pregen_thread: Optional[threading.Thread] = None
        self._stop_pregen = threading.Event()
        self._blocks_dir = Path(BLOCKS_DIR)
        try:
            self._blocks_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            LOGGER.warning("Failed to create blocks directory %s: %s. Blocks will be stored in memory only.", self._blocks_dir, e)
            # Continue without persistent storage - blocks will only be in memory
        # Cache for pre-generated blocks, keyed by spec hash
        self._pregenerated_blocks: Dict[str, BumperBlock] = {}
        # Index of pre-generated blocks by episode path for quick lookup
        self._blocks_by_episode: Dict[str, BumperBlock] = {}
    
    def _spec_hash(self, up_next_bumper: Optional[str], sassy_card: Optional[str], 
                   network_bumper: Optional[str], weather_bumper: Optional[str]) -> str:
        """Generate a hash for a block specification."""
        spec_str = f"{up_next_bumper}|{sassy_card}|{network_bumper}|{weather_bumper}"
        return hashlib.md5(spec_str.encode()).hexdigest()
    
    def peek_next_pregenerated_block(self, episode_path: Optional[str] = None) -> Optional[BumperBlock]:
        """Peek at the next pre-generated block without removing it (for preview).
        
        If episode_path is provided, returns the block for that episode.
        Otherwise, returns the first available block (FIFO).
        """
        with self._pregen_lock:
            if episode_path and episode_path in self._blocks_by_episode:
                return self._blocks_by_episode[episode_path]
            
            # Return first available block (FIFO)
            if self._pregenerated_blocks:
                first_hash = next(iter(self._pregenerated_blocks.keys()))
                return self._pregenerated_blocks[first_hash]
        
        return None
    
    def get_next_pregenerated_block(self, episode_path: Optional[str] = None) -> Optional[BumperBlock]:
        """Get the next pre-generated block, optionally matching a specific episode.
        
        Removes the block from cache. Use peek_next_pregenerated_block() for preview.
        
        If episode_path is provided, returns the block for that episode.
        Otherwise, returns the first available block (FIFO).
        """
        with self._pregen_lock:
            if episode_path and episode_path in self._blocks_by_episode:
                block = self._blocks_by_episode.pop(episode_path)
                # Also remove from main cache
                for spec_hash, cached_block in list(self._pregenerated_blocks.items()):
                    if cached_block == block:
                        del self._pregenerated_blocks[spec_hash]
                        break
                LOGGER.info(
                    "Retrieved pre-generated block for episode %s (bumpers: %d, remaining: %d)",
                    Path(episode_path).name if episode_path else "unknown",
                    len(block.bumpers) if block else 0,
                    len(self._pregenerated_blocks),
                )
                return block
            
            # Return first available block (FIFO)
            if self._pregenerated_blocks:
                first_hash = next(iter(self._pregenerated_blocks.keys()))
                block = self._pregenerated_blocks.pop(first_hash)
                # Remove from episode index if present
                if block.episode_path and block.episode_path in self._blocks_by_episode:
                    del self._blocks_by_episode[block.episode_path]
                LOGGER.info(
                    "Retrieved first available pre-generated block (bumpers: %d, remaining: %d)",
                    len(block.bumpers) if block else 0,
                    len(self._pregenerated_blocks),
                )
                return block
        
        return None
    
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
        with self._pregen_lock:
            cache_size = len(self._pregenerated_blocks)
        LOGGER.debug(
            "get_pregenerated_block: up_next=%s, cache_size=%d",
            Path(up_next_bumper).name if up_next_bumper else None,
            cache_size,
        )
        # First try exact match
        spec_hash = self._spec_hash(up_next_bumper, sassy_card, network_bumper, weather_bumper)
        with self._pregen_lock:
            if spec_hash in self._pregenerated_blocks:
                block = self._pregenerated_blocks.pop(spec_hash)
                # Clean up episode_path index if present
                if block.episode_path and block.episode_path in self._blocks_by_episode:
                    # Only remove if it's the same block (by object identity)
                    if self._blocks_by_episode[block.episode_path] is block:
                        del self._blocks_by_episode[block.episode_path]
                LOGGER.info(
                    "Retrieved pre-generated bumper block (exact match) %s (bumpers: %d, remaining cache: %d)",
                    spec_hash[:8],
                    len(block.bumpers) if block and block.bumpers else 0,
                    len(self._pregenerated_blocks),
                )
                return block
            
            # If sassy_card is None, try to find any block with matching up_next_bumper
            # This allows us to use pre-generated blocks even if sassy card differs
            if sassy_card is None and up_next_bumper:
                # First try matching by hash with None for sassy (in case block was queued that way)
                test_hash = self._spec_hash(up_next_bumper, None, None, weather_bumper if weather_bumper else None)
                if test_hash in self._pregenerated_blocks:
                    block = self._pregenerated_blocks.pop(test_hash)
                    # Clean up episode_path index
                    if block.episode_path and block.episode_path in self._blocks_by_episode:
                        if self._blocks_by_episode[block.episode_path] is block:
                            del self._blocks_by_episode[block.episode_path]
                    LOGGER.info(
                        "Retrieved pre-generated bumper block (hash match with None sassy) %s (bumpers: %d)",
                        test_hash[:8],
                        len(block.bumpers) if block and block.bumpers else 0,
                    )
                    return block
                
                # Try with just up_next (no weather)
                test_hash = self._spec_hash(up_next_bumper, None, None, None)
                if test_hash in self._pregenerated_blocks:
                    block = self._pregenerated_blocks.pop(test_hash)
                    # Clean up episode_path index
                    if block.episode_path and block.episode_path in self._blocks_by_episode:
                        if self._blocks_by_episode[block.episode_path] is block:
                            del self._blocks_by_episode[block.episode_path]
                    LOGGER.info(
                        "Retrieved pre-generated bumper block (hash match up_next only) %s (bumpers: %d)",
                        test_hash[:8],
                        len(block.bumpers) if block and block.bumpers else 0,
                    )
                    return block
                
                # Iterate through all pre-generated blocks to find one with matching up_next
                # Check the block's actual bumpers list to see if it contains our up_next_bumper
                for cached_hash, cached_block in list(self._pregenerated_blocks.items()):
                    if cached_block and cached_block.bumpers:
                        # Check if this block contains our up_next_bumper
                        # The up_next_bumper should be in the bumpers list (typically 3rd position)
                        if up_next_bumper in cached_block.bumpers:
                            block = self._pregenerated_blocks.pop(cached_hash)
                            # Clean up episode_path index
                            if block.episode_path and block.episode_path in self._blocks_by_episode:
                                if self._blocks_by_episode[block.episode_path] is block:
                                    del self._blocks_by_episode[block.episode_path]
                            LOGGER.info(
                                "Retrieved pre-generated bumper block (up_next match in bumpers) %s (bumpers: %d)",
                                cached_hash[:8],
                                len(block.bumpers) if block and block.bumpers else 0,
                            )
                            return block
                
                # Last resort: return the first available block (FIFO)
                # This ensures we use pre-generated blocks rather than generating new ones
                if self._pregenerated_blocks:
                    first_hash = next(iter(self._pregenerated_blocks.keys()))
                    block = self._pregenerated_blocks.pop(first_hash)
                    # Clean up episode_path index
                    if block.episode_path and block.episode_path in self._blocks_by_episode:
                        if self._blocks_by_episode[block.episode_path] is block:
                            del self._blocks_by_episode[block.episode_path]
                    LOGGER.info(
                        "Retrieved pre-generated bumper block (first available) %s (bumpers: %d)",
                        first_hash[:8],
                        len(block.bumpers) if block and block.bumpers else 0,
                    )
                    return block
        
        LOGGER.debug("No pre-generated block found matching criteria")
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
                from server.generate_playlist import SASSY_CARDS, SASSY_BUMPERS_DIR
                sassy_card = SASSY_CARDS.draw_card()
                if not sassy_card:
                    LOGGER.warning("SASSY_CARDS.draw_card() returned None - trying to find existing sassy cards")
                    # Fallback: try to find any existing sassy card
                    if os.path.exists(SASSY_BUMPERS_DIR):
                        import glob
                        existing_cards = glob.glob(os.path.join(SASSY_BUMPERS_DIR, "sassy_*.mp4"))
                        if existing_cards:
                            sassy_card = existing_cards[0]
                            LOGGER.info("Using existing sassy card as fallback: %s", sassy_card)
                        else:
                            LOGGER.error("No sassy cards found in %s", SASSY_BUMPERS_DIR)
                    else:
                        LOGGER.error("Sassy bumpers directory does not exist: %s", SASSY_BUMPERS_DIR)
            except Exception as e:
                LOGGER.error("Failed to draw sassy card: %s", e, exc_info=True)
                sassy_card = None
        
        # Auto-draw network bumper if not provided
        if network_bumper is None:
            try:
                from server.generate_playlist import NETWORK_BUMPERS
                network_bumper = NETWORK_BUMPERS.draw_bumper()
                if not network_bumper:
                    LOGGER.debug("NETWORK_BUMPERS.draw_bumper() returned None - network bumper may not be due yet")
            except Exception as e:
                LOGGER.error("Failed to draw network bumper: %s", e, exc_info=True)
                network_bumper = None
        
        # Track if weather was originally requested (before JIT rendering)
        weather_was_requested = weather_bumper == "WEATHER_BUMPER"
        
        # Handle weather bumper marker - render JIT if requested
        if weather_was_requested:
            try:
                from server.stream import _render_weather_bumper_jit
                weather_bumper = _render_weather_bumper_jit()
            except Exception as e:
                LOGGER.warning("Failed to render weather bumper JIT: %s", e)
                weather_bumper = None
        
        sassy_exists = sassy_card and os.path.exists(sassy_card)
        weather_exists = weather_bumper and os.path.exists(weather_bumper)
        up_next_exists = up_next_bumper and os.path.exists(up_next_bumper)
        network_exists = network_bumper and os.path.exists(network_bumper)

        # Log detailed status for debugging
        LOGGER.debug(
            "Bumper block status: sassy=%s (%s), weather=%s (%s), up_next=%s (%s), network=%s (%s)",
            bool(sassy_exists),
            sassy_card if sassy_card else "None",
            bool(weather_exists),
            weather_bumper if weather_bumper else "None",
            bool(up_next_exists),
            up_next_bumper if up_next_bumper else "None",
            bool(network_exists),
            network_bumper if network_bumper else "None",
        )

        # Require sassy and up_next, but weather is optional
        # Weather might not be generated if API key is missing or disabled
        if not (sassy_exists and up_next_exists):
            error_msg = (
                f"Incomplete bumper block spec - missing required bumpers:\n"
                f"  sassy_card: {'exists' if sassy_exists else 'MISSING'} ({sassy_card or 'None'})\n"
                f"  up_next_bumper: {'exists' if up_next_exists else 'MISSING'} ({up_next_bumper or 'None'})\n"
                f"  weather_bumper: {'exists' if weather_exists else 'optional/missing'} ({weather_bumper or 'None'})\n"
                f"  network_bumper: {'exists' if network_exists else 'optional/missing'} ({network_bumper or 'None'})"
            )
            LOGGER.error(error_msg)
            return None
        
        # If weather was requested but is missing, log a warning but continue
        if weather_was_requested and not weather_exists:
            LOGGER.warning("Weather bumper was requested but not available, continuing without it")

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
        original_bumpers_to_cleanup = []  # Track original bumpers for cleanup
        cumulative_offset = 0.0
        for bumper_path, duration in bumper_entries:
            if skip_music or not music_track:
                block_bumpers.append(bumper_path)
                # Track for cleanup if it's a generated up-next bumper
                if "/bumpers/up_next/" in bumper_path:
                    original_bumpers_to_cleanup.append(bumper_path)
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
                        # Track original bumper for cleanup if it's a generated up-next bumper
                        if "/bumpers/up_next/" in bumper_path:
                            original_bumpers_to_cleanup.append(bumper_path)
                    else:
                        # Fallback: use original
                        block_bumpers.append(bumper_path)
                        if "/bumpers/up_next/" in bumper_path:
                            original_bumpers_to_cleanup.append(bumper_path)
                except Exception as e:
                    LOGGER.error("Failed to add music to bumper %s: %s", bumper_path, e, exc_info=True)
                    # Fallback: use original bumper
                    if os.path.exists(bumper_path):
                        LOGGER.warning("Using original bumper without music as fallback: %s", bumper_path)
                        block_bumpers.append(bumper_path)
                        if "/bumpers/up_next/" in bumper_path:
                            original_bumpers_to_cleanup.append(bumper_path)
                    else:
                        LOGGER.error("Original bumper file missing: %s", bumper_path)
            cumulative_offset += duration
        
        if not block_bumpers:
            return None
        
        # Store cleanup info in the block
        block = BumperBlock(
            bumpers=block_bumpers,
            music_track=music_track,
            block_id=block_id
        )
        
        # Attach cleanup list to block (using a private attribute)
        block._cleanup_bumpers = original_bumpers_to_cleanup
        
        return block
    
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
            LOGGER.error("Failed to add music to bumper: %s", e, exc_info=True)
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
        """Queue a bumper block for pre-generation.
        
        Checks for duplicates to avoid redundant work:
        - If already cached, skip
        - If already queued, skip
        - Otherwise, add to queue
        """
        episode_path = block_spec.get("episode_path")
        up_next_bumper = block_spec.get("up_next_bumper")
        
        with self._pregen_lock:
            # Check if already cached by episode path
            if episode_path and episode_path in self._blocks_by_episode:
                LOGGER.debug(
                    "Skipping pre-generation queue - block already cached for episode %s",
                    Path(episode_path).name if episode_path else "unknown"
                )
                return
            
            # Check if already cached by spec hash
            spec_hash = self._spec_hash(
                up_next_bumper,
                block_spec.get("sassy_card"),
                block_spec.get("network_bumper"),
                block_spec.get("weather_bumper"),
            )
            if spec_hash in self._pregenerated_blocks:
                LOGGER.debug(
                    "Skipping pre-generation queue - block already cached with hash %s",
                    spec_hash[:8]
                )
                return
            
            # Check if already queued (by episode path or spec hash)
            for queued_spec in self._pregen_queue:
                queued_episode = queued_spec.get("episode_path")
                queued_hash = self._spec_hash(
                    queued_spec.get("up_next_bumper"),
                    queued_spec.get("sassy_card"),
                    queued_spec.get("network_bumper"),
                    queued_spec.get("weather_bumper"),
                )
                if (episode_path and queued_episode == episode_path) or queued_hash == spec_hash:
                    LOGGER.debug(
                        "Skipping pre-generation queue - block already queued for episode %s",
                        Path(episode_path).name if episode_path else "unknown"
                    )
                    return
            
            # Not cached or queued - add to queue
            self._pregen_queue.append(block_spec)
            queue_size = len(self._pregen_queue)
            cache_size = len(self._pregenerated_blocks)
        
        LOGGER.info(
            "Added block to pre-generation queue (queue size: %d, cache size: %d, up_next: %s, episode: %s)",
            queue_size,
            cache_size,
            Path(up_next_bumper).name if up_next_bumper else None,
            Path(episode_path).name if episode_path else "unknown",
        )
    
    def start_pregen_thread(self) -> None:
        """Start the pre-generation thread."""
        if self._pregen_thread and self._pregen_thread.is_alive():
            return
        
        self._stop_pregen.clear()
        self._pregen_thread = threading.Thread(
            target=self._pregen_worker,
            daemon=False,  # Keep thread alive even if main thread exits
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
        LOGGER.info("Pre-generation worker thread started")
        while not self._stop_pregen.is_set():
            block_spec = None
            with self._pregen_lock:
                if self._pregen_queue:
                    block_spec = self._pregen_queue.pop(0)
                    remaining = len(self._pregen_queue)
            
            if block_spec:
                up_next = block_spec.get("up_next_bumper")
                LOGGER.info(
                    "Pre-generation worker: Processing block from queue (up_next: %s, remaining in queue: %d)",
                    Path(up_next).name if up_next else None,
                    remaining if block_spec else 0,
                )
                try:
                    # Generate block with music (for pre-generation)
                    # Remove episode_path from spec as it's not a parameter of generate_block()
                    gen_spec = {k: v for k, v in block_spec.items() if k != "episode_path"}
                    block = self.generate_block(**gen_spec, skip_music=False)
                    if block:
                        # Store in cache for later retrieval
                        spec_hash = self._spec_hash(
                            block_spec.get("up_next_bumper"),
                            block_spec.get("sassy_card"),
                            block_spec.get("network_bumper"),
                            block_spec.get("weather_bumper"),
                        )
                        # Store episode_path if provided
                        episode_path = block_spec.get("episode_path")
                        if episode_path:
                            block.episode_path = episode_path
                        
                        with self._pregen_lock:
                            # Check if spec_hash already exists (shouldn't happen, but be safe)
                            if spec_hash in self._pregenerated_blocks:
                                LOGGER.warning(
                                    "Pre-generation worker: Spec hash %s already exists in cache, overwriting",
                                    spec_hash[:8]
                                )
                                # Clean up old episode_path entry if present
                                old_block = self._pregenerated_blocks[spec_hash]
                                if old_block.episode_path and old_block.episode_path in self._blocks_by_episode:
                                    if self._blocks_by_episode[old_block.episode_path] is old_block:
                                        del self._blocks_by_episode[old_block.episode_path]
                            
                            # Check if episode_path already exists with different block (shouldn't happen)
                            if episode_path and episode_path in self._blocks_by_episode:
                                existing_block = self._blocks_by_episode[episode_path]
                                if existing_block is not block:
                                    LOGGER.warning(
                                        "Pre-generation worker: Episode path %s already has a different block cached, overwriting",
                                        Path(episode_path).name if episode_path else "unknown"
                                    )
                                    # Remove old block from main cache if present
                                    for old_hash, old_block in list(self._pregenerated_blocks.items()):
                                        if old_block is existing_block:
                                            del self._pregenerated_blocks[old_hash]
                                            break
                            
                            # Store the new block
                            self._pregenerated_blocks[spec_hash] = block
                            if episode_path:
                                self._blocks_by_episode[episode_path] = block
                            cache_size = len(self._pregenerated_blocks)
                        LOGGER.info(
                            "Pre-generation worker: Successfully generated and cached block %s for episode %s (cache size: %d, bumpers: %d)",
                            spec_hash[:8],
                            Path(episode_path).name if episode_path else "unknown",
                            cache_size,
                            len(block.bumpers) if block else 0,
                        )
                    else:
                        LOGGER.warning(
                            "Pre-generation worker: Block generation returned None for episode %s (up_next: %s)",
                            Path(block_spec.get("episode_path", "")).name if block_spec.get("episode_path") else "unknown",
                            Path(up_next).name if up_next else None,
                        )
                except Exception as e:
                    LOGGER.error(
                        "Pre-generation worker: Failed to pre-generate bumper block for episode %s (up_next: %s): %s",
                        Path(block_spec.get("episode_path", "")).name if block_spec.get("episode_path") else "unknown",
                        Path(up_next).name if up_next else None,
                        e,
                        exc_info=True
                    )
            else:
                # No work, sleep briefly
                time.sleep(0.5)


# Global instance with thread-safe initialization
_generator: Optional[BumperBlockGenerator] = None
_generator_lock = threading.Lock()


def get_generator() -> BumperBlockGenerator:
    """Get the global bumper block generator instance (thread-safe singleton)."""
    global _generator
    if _generator is None:
        with _generator_lock:
            # Double-check pattern to avoid race condition
            if _generator is None:
                _generator = BumperBlockGenerator()
    return _generator

