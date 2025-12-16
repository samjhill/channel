#!/usr/bin/env python3

import logging
import os
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

LOGGER = logging.getLogger(__name__)

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent
if (REPO_ROOT / "scripts").exists():
    sys.path.insert(0, str(REPO_ROOT))

if (REPO_ROOT / "server").exists():
    sys.path.insert(0, str(REPO_ROOT))

from scripts.bumpers.render_up_next import render_up_next_bumper
from scripts.bumpers.render_sassy_card import (
    load_sassy_config as load_sassy_card_config,
    render_sassy_card,
)
from scripts.bumpers.render_network_brand import render_network_brand_bumper
from server.api.settings_service import load_settings
from server.playlist_service import (
    get_last_watched_episode,
    is_episode_entry,
    resolve_playlist_path,
)
from server.services.weather_service import load_weather_config
from server.bumper_block import BUMPER_BLOCK_MARKER, get_generator

PLAYLIST_FILE = str(resolve_playlist_path())
DEFAULT_ASSETS_ROOT = "/app/assets"
DEFAULT_PLAYLIST_EPISODE_LIMIT = 500
DEFAULT_PLAYLIST_SEED_LIMIT = 12
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov")
SEASON_PATTERN = re.compile(r"(?:season|series)\s*\d+", re.IGNORECASE)
EPISODE_PATTERN = re.compile(r"S\d{1,2}E\d{1,2}.*$", re.IGNORECASE)
EPISODE_CODE_PATTERN = re.compile(r"[sS](\d{1,2})[ ._\-]*[eE](\d{1,2})")
ALT_EPISODE_CODE_PATTERN = re.compile(r"(\d{1,2})x(\d{1,2})", re.IGNORECASE)
SEASON_ONLY_PATTERN = re.compile(r"season[ ._\-]*(\d{1,2})", re.IGNORECASE)
EPISODE_ONLY_PATTERN = re.compile(r"(?:episode|ep)[ ._\-]*(\d{1,3})", re.IGNORECASE)


def _clean_segment(text: str) -> str:
    cleaned = text.replace("_", " ").replace(".", " ").strip()
    cleaned = re.split(r"[\[\]/]", cleaned)[0].strip()
    cleaned = EPISODE_PATTERN.sub("", cleaned).strip()
    return cleaned


def infer_show_title_from_path(file_path: str) -> str:
    path = Path(file_path)
    parent_name = path.parent.name or ""
    candidate = parent_name or path.stem

    if parent_name and SEASON_PATTERN.search(parent_name):
        ancestor = path.parent.parent.name
        if ancestor:
            candidate = ancestor

    candidate = _clean_segment(candidate) or "Up Next"
    return candidate.title()


def safe_filename(title: str) -> str:
    safe_chars = [c.lower() if c.isalnum() else "_" for c in title.strip()]
    sanitized = "".join(safe_chars).strip("_")
    return sanitized or "show"


def extract_episode_metadata(episode_path: str) -> Dict[str, Optional[int]]:
    """
    Attempt to parse season / episode numbers from the file path.
    """
    path = Path(episode_path)
    candidates = [
        path.stem,
        path.name,
    ]
    # Include last few directory names for clues such as "Season 02"
    parents = [part for part in path.parts[-3:]]
    candidates.extend(parents)

    season: Optional[int] = None
    episode_num: Optional[int] = None

    for text in candidates:
        match = EPISODE_CODE_PATTERN.search(text)
        if match:
            season = season or int(match.group(1))
            episode_num = episode_num or int(match.group(2))
            if season is not None and episode_num is not None:
                break
        match_alt = ALT_EPISODE_CODE_PATTERN.search(text)
        if match_alt:
            season = season or int(match_alt.group(1))
            episode_num = episode_num or int(match_alt.group(2))
            if season is not None and episode_num is not None:
                break

    if season is None:
        for text in reversed(parents):
            match = SEASON_ONLY_PATTERN.search(text)
            if match:
                season = int(match.group(1))
                break

    if episode_num is None:
        for text in candidates:
            match = EPISODE_ONLY_PATTERN.search(text)
            if match:
                episode_num = int(match.group(1))
                break

    return {"season": season, "episode": episode_num}


def format_episode_code(metadata: Optional[Dict[str, Optional[int]]]) -> Optional[str]:
    if not metadata:
        return None
    season = metadata.get("season")
    episode_num = metadata.get("episode")
    if season is not None and episode_num is not None:
        return f"S{season:02d}E{episode_num:02d}"
    if episode_num is not None:
        return f"E{episode_num:02d}"
    if season is not None:
        return f"S{season:02d}"
    return None


def format_episode_label(metadata: Optional[Dict[str, Optional[int]]]) -> Optional[str]:
    if not metadata:
        return None
    season = metadata.get("season")
    episode_num = metadata.get("episode")
    parts = []
    if season is not None:
        parts.append(f"Season {season}")
    if episode_num is not None:
        parts.append(f"Episode {episode_num}")

    human_label = " / ".join(parts)
    code = format_episode_code(metadata)
    if human_label and code:
        return f"{human_label} ({code})"
    return human_label or code


def find_existing_bumper(
    show_title: str, episode_metadata: Optional[Dict[str, Optional[int]]] = None
) -> Optional[str]:
    """
    Check if a bumper already exists for the given show/episode.
    Validates that the bumper is a valid video file before returning it.
    Returns the path to the bumper if found and valid, None otherwise.
    Does not create new bumpers.
    
    NOTE: Specific-episode bumpers are now generated dynamically (JIT).
    This function only returns generic bumpers (show.mp4), not specific ones (show_S01E02.mp4).
    """
    base_name = safe_filename(show_title)
    
    LOGGER.debug("find_existing_bumper: Looking for bumper - Show=%s, BaseName=%s", show_title, base_name)
    
    # Skip specific-episode bumpers - they are generated dynamically
    # Only return generic bumpers that exist as files
    
    # Check for generic bumper
    generic_filename = f"{base_name}.mp4"
    generic_bumper_path = os.path.join(BUMPERS_DIR, generic_filename)
    if os.path.exists(generic_bumper_path) and _validate_bumper_file(generic_bumper_path):
        LOGGER.debug("find_existing_bumper: Found exact match: %s", generic_filename)
        return generic_bumper_path
    
    # If exact match fails, try fuzzy matching: extract just the show name
    # (strip out release group, quality, year, etc.)
    # For example: "Batman The Animated Series 1991 S01 Bluray..." -> "Batman The Animated Series"
    import re
    # Try to extract just the show name by removing common patterns
    simplified_title = show_title
    # Remove year patterns (e.g., "1991", "2023")
    simplified_title = re.sub(r'\s+\d{4}\s+', ' ', simplified_title, flags=re.IGNORECASE)
    # Remove quality/format patterns (e.g., "1080p", "Bluray", "x265", etc.)
    quality_patterns = [
        r'\b(bluray|blu-ray|dvd|webdl|web-dl|hdtv|bdrip|dvdrip)\b',
        r'\b(1080p|720p|480p|2160p|4k)\b',
        r'\b(x264|x265|h264|h265|hevc|avc)\b',
        r'\b(eac3|ac3|aac|dts|mp3)\b',
        r'\b(2\.0|5\.1|7\.1)\b',
        r'\b(s01|s02|season\s*\d+)\b',  # Season info
        r'\b(i\w+|\d+)\b',  # Release group names (single word or number)
    ]
    for pattern in quality_patterns:
        simplified_title = re.sub(pattern, '', simplified_title, flags=re.IGNORECASE)
    # Clean up extra spaces
    simplified_title = ' '.join(simplified_title.split())
    # Take first 3-4 words as the show name (usually enough to identify the show)
    words = simplified_title.split()
    if len(words) > 4:
        simplified_title = ' '.join(words[:4])
    
    if simplified_title and simplified_title.lower() != base_name.lower():
        simplified_base = safe_filename(simplified_title)
        # Try simplified generic bumper
        simplified_filename = f"{simplified_base}.mp4"
        simplified_bumper_path = os.path.join(BUMPERS_DIR, simplified_filename)
        if os.path.exists(simplified_bumper_path) and _validate_bumper_file(simplified_bumper_path):
            LOGGER.info("find_existing_bumper: Found bumper using simplified show name: %s -> %s (%s)", 
                       show_title, simplified_title, simplified_filename)
            return simplified_bumper_path
        else:
            LOGGER.debug("find_existing_bumper: Simplified bumper not found: %s", simplified_filename)

    LOGGER.debug("find_existing_bumper: No bumper found for %s", show_title)
    return None


def _validate_bumper_file(bumper_path: str) -> bool:
    """
    Validate that a bumper file is a valid video file.
    Returns True if valid, False otherwise.
    """
    try:
        from scripts.bumpers.ffmpeg_utils import validate_video_file
        from pathlib import Path
        return validate_video_file(Path(bumper_path), min_duration_sec=0.5)
    except Exception as e:
        LOGGER.warning("Failed to validate bumper file %s: %s", bumper_path, e)
        return False


def _render_bumper_safe(
    show_title: str, episode_metadata: Optional[Dict[str, Optional[int]]] = None
) -> Tuple[str, Optional[str]]:
    """
    Safely render a bumper, returning (bumper_path, error_message).
    Designed for parallel execution.
    """
    try:
        bumper_path = ensure_bumper(show_title, episode_metadata)
        return (bumper_path, None)
    except Exception as exc:
        error_msg = str(exc)
        # Log full error with traceback to help diagnose FFmpeg issues
        LOGGER.error("Failed to render bumper for %r: %s", show_title, error_msg, exc_info=True)
        return (None, error_msg)


def ensure_bumper(
    show_title: str, episode_metadata: Optional[Dict[str, Optional[int]]] = None
) -> str:
    """
    Ensure a generic bumper exists for the given show.
    Returns the path to an existing generic bumper, or creates and returns a new one.
    Uses fast renderer with pre-generated backgrounds for efficiency.
    
    NOTE: Specific-episode bumpers are now generated dynamically (JIT) and are not
    saved as files. This function only creates/returns generic bumpers (show.mp4).
    """
    os.makedirs(BUMPERS_DIR, exist_ok=True)

    # Check if bumper already exists
    existing = find_existing_bumper(show_title, episode_metadata)
    if existing:
        return existing

    base_name = safe_filename(show_title)

    # Try fast renderer first (uses pre-generated backgrounds)
    # But only if backgrounds exist, otherwise skip directly to full render
    try:
        from scripts.bumpers.render_up_next_fast import render_up_next_bumper_fast, get_up_next_background_path
        
        # Check if backgrounds exist before trying fast render
        bg_available = get_up_next_background_path() is not None
        
        if bg_available:
            import random
            
            # Pick a random background for variety
            background_id = random.randint(0, 4)  # Use backgrounds 0-4
            
            # First, ensure generic bumper exists (without episode info)
            generic_filename = f"{base_name}.mp4"
            generic_bumper_path = os.path.join(BUMPERS_DIR, generic_filename)
            if not os.path.exists(generic_bumper_path):
                LOGGER.info("Rendering generic 'Up Next' bumper for %r (fast)", show_title)
                success = render_up_next_bumper_fast(
                    show_title=show_title,
                    output_path=generic_bumper_path,
                    episode_label=None,
                    background_id=background_id,
                )
                if not success:
                    raise RuntimeError("Fast render failed")
        else:
            # No backgrounds available, skip fast render and go straight to fallback
            LOGGER.debug("No up-next backgrounds available, skipping fast render")
            raise ImportError("Backgrounds not available")
        
        # Specific-episode bumpers are now generated dynamically (JIT), not saved as files
        # Return generic bumper (specific-episode bumpers will be rendered on-demand)
        return generic_bumper_path
    
    except Exception as e:
        # Fallback to full renderer if fast render fails
        LOGGER.warning("Fast render failed, falling back to full render: %s", e, exc_info=True)
        from scripts.bumpers.render_up_next import render_up_next_bumper
        
        # First, ensure generic bumper exists (without episode info)
        generic_filename = f"{base_name}.mp4"
        generic_bumper_path = os.path.join(BUMPERS_DIR, generic_filename)
        if not os.path.exists(generic_bumper_path):
            LOGGER.info("Rendering generic 'Up Next' bumper for %r", show_title)
            try:
                render_up_next_bumper(
                    show_title=show_title,
                    output_path=generic_bumper_path,
                    logo_path=os.path.join(ASSETS_ROOT, "branding", "hbn_logo_bug.png"),
                    episode_label=None,  # Generic bumper has no episode label
                )
            except Exception as render_error:
                # Log the full error including FFmpeg stderr if available
                LOGGER.error("Full render also failed for %r: %s", show_title, render_error, exc_info=True)
                raise

        # Specific-episode bumpers are now generated dynamically (JIT), not saved as files
        # Return generic bumper (specific-episode bumpers will be rendered on-demand)
        return generic_bumper_path


def resolve_assets_root() -> str:
    """
    Resolve the root directory for static assets (logos, fonts, etc.).
    This remains under /app/assets by default but can be overridden via
    HBN_ASSETS_ROOT for local development.
    """
    override = os.environ.get("HBN_ASSETS_ROOT")
    if override:
        return override

    if os.path.isdir(DEFAULT_ASSETS_ROOT):
        return DEFAULT_ASSETS_ROOT

    repo_guess = os.path.abspath(
        os.path.join(Path(__file__).resolve().parent.parent, "assets")
    )
    if os.path.isdir(repo_guess):
        return repo_guess

    return DEFAULT_ASSETS_ROOT


def _normalize_path_for_container(path: str) -> str:
    """
    Normalize path when running inside Docker container.
    Converts host paths like /Volumes/media/tv to container paths like /media/tvchannel.
    """
    # Check if we're running inside Docker (container has /app directory)
    if os.path.exists("/app"):
        # Common host-to-container path mappings
        # /Volumes/media/tv -> /media/tvchannel
        if path.startswith("/Volumes/media/tv"):
            return path.replace("/Volumes/media/tv", "/media/tvchannel", 1)
        # Handle other common macOS/Windows volume mount patterns
        if path.startswith("/Volumes/"):
            # Generic fallback: try /media/tvchannel if it exists
            if os.path.exists("/media/tvchannel"):
                return "/media/tvchannel"
    return path


def resolve_bumpers_root(assets_root: str) -> str:
    """
    Resolve the root directory for generated bumper videos.

    By default this lives under the assets tree:
        <ASSETS_ROOT>/bumpers

    but can be moved to an external volume (e.g. alongside your TV media)
    by setting:

        HBN_BUMPERS_ROOT=/media/tvchannel/bumpers

    This keeps large rendered videos out of the Docker image and lets them
    be shared across rebuilds.

    If running inside Docker and HBN_BUMPERS_ROOT is not set, defaults to
    /media/tvchannel/bumpers to match the media volume mount.
    """
    override = os.environ.get("HBN_BUMPERS_ROOT")
    if override:
        # Normalize path for container if needed (like media_root)
        return _normalize_path_for_container(override)

    # If running inside Docker, default to media volume bumpers directory
    if os.path.exists("/app"):
        # Check if /media/tvchannel/bumpers exists or can be created
        media_bumpers = "/media/tvchannel/bumpers"
        if os.path.exists("/media/tvchannel") or os.path.exists(media_bumpers):
            return media_bumpers

    return os.path.join(assets_root, "bumpers")


ASSETS_ROOT = resolve_assets_root()
BUMPERS_ROOT = resolve_bumpers_root(ASSETS_ROOT)
BUMPERS_DIR = os.path.join(BUMPERS_ROOT, "up_next")
SASSY_BUMPERS_DIR = os.path.join(BUMPERS_ROOT, "sassy")
NETWORK_BUMPERS_DIR = os.path.join(BUMPERS_ROOT, "network")
try:
    PLAYLIST_EPISODE_LIMIT = max(
        1,
        int(os.environ.get("PLAYLIST_EPISODE_LIMIT", DEFAULT_PLAYLIST_EPISODE_LIMIT)),
    )
except (TypeError, ValueError):
    PLAYLIST_EPISODE_LIMIT = DEFAULT_PLAYLIST_EPISODE_LIMIT

try:
    PLAYLIST_SEED_LIMIT = max(
        0,
        int(os.environ.get("PLAYLIST_SEED_LIMIT", DEFAULT_PLAYLIST_SEED_LIMIT)),
    )
except (TypeError, ValueError):
    PLAYLIST_SEED_LIMIT = DEFAULT_PLAYLIST_SEED_LIMIT

# Maximum number of parallel bumper generation workers
try:
    BUMPER_GEN_MAX_WORKERS = max(
        1,
        int(os.environ.get("BUMPER_GEN_MAX_WORKERS", os.cpu_count() or 4)),
    )
except (TypeError, ValueError):
    BUMPER_GEN_MAX_WORKERS = 4


def parse_include_overrides() -> set[str]:
    env_value = os.environ.get("INCLUDE_SHOWS", "")
    if not env_value.strip():
        return set()
    return {token.strip().lower() for token in env_value.split(",") if token.strip()}


ENV_INCLUDE_FILTER = parse_include_overrides()


@dataclass(frozen=True)
class EpisodeSlot:
    show_label: str
    episode_path: str


class SassyCardManager:
    """
    Handles config loading, bumper generation, and deck shuffling for sassy cards.
    """

    def __init__(self) -> None:
        self._config: Optional[Dict[str, Any]] = None
        self._cards: Optional[List[str]] = None
        self._deck: List[str] = []
        self._logo_path: Optional[str] = None

    def config(self) -> Dict[str, Any]:
        if self._config is None:
            self._config = load_sassy_card_config()
        return self._config

    def enabled(self) -> bool:
        return bool(self.config().get("enabled", False))

    def probability(self) -> float:
        try:
            return max(
                0.0, float(self.config().get("probability_between_episodes", 0.0))
            )
        except (TypeError, ValueError):
            return 0.0

    def _resolve_logo_path(self) -> Optional[str]:
        if self._logo_path is None:
            candidate = os.path.join(ASSETS_ROOT, "branding", "hbn_logo_bug.png")
            self._logo_path = candidate if os.path.isfile(candidate) else None
        return self._logo_path

    def _ensure_cards(self) -> List[str]:
        if self._cards is not None:
            return self._cards

        os.makedirs(SASSY_BUMPERS_DIR, exist_ok=True)
        cfg = self.config()
        logo_path = self._resolve_logo_path()
        cards: List[str] = []

        for idx, message in enumerate(cfg.get("messages", []), start=1):
            slug = safe_filename(message) or f"card_{idx}"
            destination = os.path.join(SASSY_BUMPERS_DIR, f"sassy_{slug}.mp4")
            if not os.path.exists(destination):
                try:
                    render_sassy_card(
                        output_path=destination,
                        logo_path=logo_path,
                        message=message,
                    )
                except Exception as exc:  # pragma: no cover - best effort
                    LOGGER.error("Failed to render sassy card for '%s': %s", message[:30], exc)
            if os.path.exists(destination):
                cards.append(destination)

        self._cards = cards
        return cards

    def reset_deck(self) -> None:
        """Reset the deck to start fresh for a new playlist generation."""
        self._deck = []

    def draw_card(self) -> Optional[str]:
        if not self.enabled():
            return None

        cards = self._ensure_cards()
        if not cards:
            return None

        # Reshuffle deck if empty
        if not self._deck:
            self._deck = cards[:]
            random.shuffle(self._deck)

        # Check probability after ensuring we have cards available
        probability = self.probability()
        if probability <= 0 or random.random() > probability:
            return None

        return self._deck.pop()


SASSY_CARDS = SassyCardManager()


class NetworkBumperManager:
    """
    Handles generation and periodic insertion of full network branding bumpers.
    Inserts approximately 1 network bumper per hour (roughly every 25-30 episodes).
    """

    def __init__(self) -> None:
        self._bumper_path: Optional[str] = None
        self._logo_path: Optional[str] = None
        self._episodes_since_last_network = 0
        self._target_interval = 28  # Roughly 1 per hour (assuming ~22 min episodes)

    def _resolve_logo_path(self) -> Optional[str]:
        if self._logo_path is None:
            svg_candidate = os.path.join(ASSETS_ROOT, "branding", "hbn_logo_full.svg")
            png_candidate = os.path.join(ASSETS_ROOT, "branding", "hbn_logo_full.png")
            if os.path.isfile(svg_candidate):
                self._logo_path = svg_candidate
            elif os.path.isfile(png_candidate):
                self._logo_path = png_candidate
        return self._logo_path

    def _ensure_bumper(self) -> Optional[str]:
        if self._bumper_path is not None and os.path.exists(self._bumper_path):
            return self._bumper_path

        os.makedirs(NETWORK_BUMPERS_DIR, exist_ok=True)
        logo_path = self._resolve_logo_path()
        if not logo_path:
            return None

        bumper_path = os.path.join(NETWORK_BUMPERS_DIR, "network_brand.mp4")
        if os.path.exists(bumper_path):
            self._bumper_path = bumper_path
            return bumper_path

        try:
            print("[Network] Rendering full network branding bumper...", flush=True)
            render_network_brand_bumper(
                output_path=bumper_path,
                logo_svg_path=logo_path,
                music_volume=0.4,
            )
            if os.path.exists(bumper_path):
                self._bumper_path = bumper_path
                return bumper_path
        except Exception as exc:  # pragma: no cover - best effort
            print(f"[Network] Failed to render network bumper: {exc}")

        return None

    def draw_bumper(self) -> Optional[str]:
        """
        Get a network bumper if it's time to insert one.
        Returns a bumper approximately once every target_interval episodes.
        """
        self._episodes_since_last_network += 1

        # Add some randomness (±5 episodes) to avoid predictable pattern
        variance = random.randint(-5, 5)
        actual_interval = self._target_interval + variance

        if self._episodes_since_last_network >= actual_interval:
            self._episodes_since_last_network = 0
            return self._ensure_bumper()

        return None


NETWORK_BUMPERS = NetworkBumperManager()

# Special marker for weather bumpers (rendered at playback time)
WEATHER_BUMPER_MARKER = "WEATHER_BUMPER"


def maybe_write_weather_bumper(handle) -> None:
    """
    Conditionally insert a weather bumper marker into the playlist.
    Weather bumpers are rendered at playback time for fresh data.
    """
    try:
        cfg = load_weather_config()
        if not cfg.get("enabled", False):
            return
        
        probability = cfg.get("probability_between_episodes", 0.0)
        if probability <= 0 or random.random() > probability:
            return
        
        handle.write(WEATHER_BUMPER_MARKER + "\n")
        handle.flush()
    except Exception as exc:
        # Best effort - if weather config is misconfigured, just skip
        LOGGER.debug("Failed to check weather config: %s", exc)


def resolve_channel(settings: Dict[str, Any]) -> Dict[str, Any]:
    channels = settings.get("channels") or []
    if not channels:
        raise RuntimeError("No channels configured in channel_settings.json")

    requested = os.environ.get("CHANNEL_ID")
    if requested:
        for channel in channels:
            if channel.get("id") == requested:
                return channel
        raise RuntimeError(f"Channel '{requested}' not found in settings.")

    return channels[0]


def filter_shows(channel: Dict[str, Any]) -> List[Dict[str, Any]]:
    shows = channel.get("shows") or []
    filtered = []
    for show in shows:
        if not show.get("include"):
            continue
        if ENV_INCLUDE_FILTER:
            compare_values = {
                str(show.get("label", "")).lower(),
                str(show.get("id", "")).lower(),
                str(show.get("path", "")).lower(),
            }
            if compare_values.isdisjoint(ENV_INCLUDE_FILTER):
                continue
        filtered.append(show)
    return filtered


def collect_show_episodes(media_root: str, show: Dict[str, Any]) -> List[str]:
    base_path = Path(media_root) / str(show.get("path") or "")
    if not base_path.exists():
        print(f"[Playlist] Show path missing: {base_path}")
        return []

    episodes: List[str] = []
    # Use pathlib for better performance
    video_exts_lower = tuple(ext.lower() for ext in VIDEO_EXTENSIONS)
    for root, _, files in os.walk(base_path):
        # Filter files first before path operations
        video_files = [fn for fn in files if fn.lower().endswith(video_exts_lower)]
        for fn in video_files:
            episodes.append(os.path.join(root, fn))
    # Sort once at the end
    episodes.sort()
    return episodes


def resolve_show_mode(channel_mode: str, show_mode: str) -> str:
    if show_mode not in {"inherit", "sequential", "random"}:
        return channel_mode
    if show_mode == "inherit":
        return channel_mode
    return show_mode


def order_episodes(episodes: List[str], mode: str) -> List[str]:
    ordered = list(episodes)
    if mode == "random":
        random.shuffle(ordered)
    return ordered


def build_episode_schedule(
    entries: Sequence[Dict[str, Any]], mode: str, episode_limit: Optional[int]
) -> List[EpisodeSlot]:
    if mode == "random":
        return schedule_weighted_random(entries, episode_limit)
    return schedule_sequential(entries, episode_limit)


def schedule_sequential(
    entries: Sequence[Dict[str, Any]], episode_limit: Optional[int]
) -> List[EpisodeSlot]:
    queues = [
        {"config": entry["config"], "episodes": list(entry["episodes"])}
        for entry in entries
        if entry["episodes"]
    ]
    slots: List[EpisodeSlot] = []
    processed = 0

    if not queues:
        return slots

    while any(queue["episodes"] for queue in queues):
        for queue in queues:
            if not queue["episodes"]:
                continue
            if episode_limit is not None and processed >= episode_limit:
                return slots

            episode = queue["episodes"].pop(0)
            show_label = queue["config"].get("label") or infer_show_title_from_path(
                episode
            )
            slots.append(EpisodeSlot(show_label=show_label, episode_path=episode))
            processed += 1
            if episode_limit is not None and processed >= episode_limit:
                return slots

    return slots


def schedule_weighted_random(
    entries: Sequence[Dict[str, Any]], episode_limit: Optional[int]
) -> List[EpisodeSlot]:
    slots: List[EpisodeSlot] = []
    active = [
        {
            "config": entry["config"],
            "episodes": list(entry["episodes"]),
            "weight": entry["weight"],
        }
        for entry in entries
        if entry["episodes"]
    ]
    processed = 0

    while active:
        if episode_limit is not None and processed >= episode_limit:
            break

        # Pre-compute weights only when needed (list might change)
        weights = [entry["weight"] for entry in active]
        chosen = random.choices(active, weights=weights, k=1)[0]
        if not chosen["episodes"]:
            active.remove(chosen)
            continue

        episode = chosen["episodes"].pop(0)
        if not chosen["episodes"]:
            active.remove(chosen)

        show_label = chosen["config"].get("label") or infer_show_title_from_path(
            episode
        )
        slots.append(EpisodeSlot(show_label=show_label, episode_path=episode))
        processed += 1

    return slots


def collect_needed_bumpers(
    slots: Sequence[EpisodeSlot], seed_threshold: int, max_blocks_ahead: int = 3
) -> List[Tuple[str, Optional[Dict[str, Optional[int]]]]]:
    """
    Collect bumpers that need to be generated for the next few bumper blocks only.
    This limits storage usage by only generating what's needed soon.
    
    Args:
        slots: Episode slots to check
        seed_threshold: Number of seed episodes to skip
        max_blocks_ahead: Maximum number of bumper blocks to generate ahead (default: 3)
    
    Returns:
        List of (show_title, episode_metadata) tuples for bumpers to generate.
    """
    needed: List[Tuple[str, Optional[Dict[str, Optional[int]]]]] = []
    seen = set()  # Track unique bumper requests to avoid duplicates
    generic_bumpers = {}  # Track which shows need generic bumpers
    # NOTE: Specific-episode bumpers are now generated dynamically (JIT), not pre-generated

    # Count bumper blocks to limit generation
    bumper_block_count = 0
    max_bumpers_to_collect = max_blocks_ahead * 2  # Rough estimate: ~2 bumpers per block

    for idx, slot in enumerate(slots):
        # Only collect bumpers for post-seed episodes
        if idx < seed_threshold:
            continue

        # Limit to next few bumper blocks
        if bumper_block_count >= max_blocks_ahead:
            break

        metadata = extract_episode_metadata(slot.episode_path)

        # Check if bumper already exists
        existing = find_existing_bumper(slot.show_label, metadata)
        if existing:
            # Still count this as a bumper block even if bumper exists
            bumper_block_count += 1
            continue

        # Only collect generic bumpers (specific-episode bumpers are generated JIT)
        key = (slot.show_label, None)
        if key not in seen:
            seen.add(key)
            generic_bumpers[slot.show_label] = None
        
        # Count bumper blocks (each episode after seed threshold represents a potential block)
        bumper_block_count += 1
        
        # Stop if we've collected enough
        if len(needed) + len(generic_bumpers) >= max_bumpers_to_collect:
            break

    # Add all generic bumpers (specific-episode bumpers are generated dynamically, not pre-generated)
    needed.extend([(show, None) for show in generic_bumpers.keys()])

    return needed


def generate_bumpers_parallel(
    needed_bumpers: List[Tuple[str, Optional[Dict[str, Optional[int]]]]],
) -> Dict[Tuple[str, Optional[str]], str]:
    """
    Generate bumpers in parallel using ThreadPoolExecutor.
    Returns a dict mapping (show_title, episode_code) to bumper_path.
    """
    if not needed_bumpers:
        return {}

    bumper_results: Dict[Tuple[str, Optional[str]], str] = {}
    completed_count = 0
    total_count = len(needed_bumpers)

    print(
        f"[Bumpers] Generating {total_count} bumpers in parallel (max {BUMPER_GEN_MAX_WORKERS} workers)...",
        flush=True,
    )

    with ThreadPoolExecutor(max_workers=BUMPER_GEN_MAX_WORKERS) as executor:
        # Submit all bumper generation tasks
        future_to_bumper = {}
        for show_title, episode_metadata in needed_bumpers:
            episode_code = (
                format_episode_code(episode_metadata) if episode_metadata else None
            )
            future = executor.submit(_render_bumper_safe, show_title, episode_metadata)
            future_to_bumper[future] = (show_title, episode_code)

        # Collect results as they complete
        for future in as_completed(future_to_bumper):
            show_title, episode_code = future_to_bumper[future]
            completed_count += 1

            try:
                bumper_path, error = future.result()
                if bumper_path:
                    bumper_results[(show_title, episode_code)] = bumper_path
                    if completed_count % 5 == 0 or completed_count == total_count:
                        percent = int(100 * completed_count / total_count)
                        print(
                            f"[Bumpers] Progress: {completed_count}/{total_count} ({percent}%)",
                            flush=True,
                        )
                elif error:
                    # Bumper generation failed, will fallback to generic or skip
                    # Print full error (may include FFmpeg stderr)
                    error_preview = error[:500] if len(error) > 500 else error
                    print(
                        f"[Bumpers] Failed to generate bumper for {show_title!r} "
                        f"{f'(episode {episode_code})' if episode_code else ''}: {error_preview}",
                        flush=True,
                    )
                    # If error is longer, log the full error separately
                    if len(error) > 500:
                        LOGGER.error("Full error for %r: %s", show_title, error)
            except Exception as exc:
                print(
                    f"[Bumpers] Unexpected error generating bumper for {show_title!r}: {exc}",
                    flush=True,
                )

    print(
        f"[Bumpers] Completed generation: {len(bumper_results)}/{total_count} successful",
        flush=True,
    )
    return bumper_results


def write_playlist_file(slots: Sequence[EpisodeSlot]) -> None:
    """
    Write the playlist file, starting from the next episode after the last watched one.
    If no watch progress exists, starts from the beginning.
    Uses parallel bumper generation for improved performance.
    """
    seed_threshold = min(PLAYLIST_SEED_LIMIT, len(slots))
    seed_announced = False

    # Find the last watched episode and resume from the next one
    # Validate that the episode still exists before using it
    last_watched = get_last_watched_episode()
    start_index = 0

    if last_watched and slots:
        # Validate that the last watched episode still exists
        if not os.path.exists(last_watched) or not os.path.isfile(last_watched):
            LOGGER.warning(
                "Last watched episode no longer exists: %s. Starting from beginning.",
                last_watched,
            )
            last_watched = None  # Reset to start from beginning

        if last_watched:
            # Find the last watched episode in the slots
            for idx, slot in enumerate(slots):
                if slot.episode_path == last_watched:
                    # Start from the next episode
                    start_index = (idx + 1) % len(slots)
                    LOGGER.info("Resuming from episode after: %s", last_watched)
                    break

    # Rotate slots to start from the resume point
    rotated_slots = list(slots[start_index:]) + list(slots[:start_index])

    # Pre-generate all needed bumpers in parallel
    needed_bumpers = collect_needed_bumpers(rotated_slots, seed_threshold)
    pre_generated_bumpers = (
        generate_bumpers_parallel(needed_bumpers) if needed_bumpers else {}
    )

    os.makedirs(os.path.dirname(PLAYLIST_FILE), exist_ok=True)
    with open(PLAYLIST_FILE, "w", encoding="utf-8") as handle:
        # Add weather bumper at the very beginning for testing (if enabled)
        try:
            cfg = load_weather_config()
            if cfg.get("enabled", False):
                handle.write(WEATHER_BUMPER_MARKER + "\n")
        except Exception:
            # If config load fails, skip the weather bumper
            pass
        
        for idx, slot in enumerate(rotated_slots):
            require_bumper = idx >= seed_threshold

            # For post-seed episodes, check pre-generated bumpers first
            if require_bumper:
                metadata = extract_episode_metadata(slot.episode_path)
                episode_code = format_episode_code(metadata) if metadata else None
                bumper_key = (slot.show_label, episode_code)

                # Check pre-generated bumpers first
                if bumper_key in pre_generated_bumpers:
                    bumper_path = pre_generated_bumpers[bumper_key]
                else:
                    # Fallback: check existing or try to generate (should be rare)
                    bumper_path = find_existing_bumper(slot.show_label, metadata)
                    if not bumper_path:
                        try:
                            bumper_path = ensure_bumper(slot.show_label, metadata)
                        except Exception as exc:
                            # Print full error (may include FFmpeg stderr)
                            error_str = str(exc)
                            error_preview = error_str[:500] if len(error_str) > 500 else error_str
                            print(
                                f"[Bumpers] Fallback generation failed for {slot.show_label}: {error_preview}",
                                flush=True,
                            )
                            # Log full error with traceback
                            LOGGER.error("Fallback generation failed for %r: %s", slot.show_label, error_str, exc_info=True)
                            bumper_path = None
            else:
                # For seed episodes, just check if bumper exists (don't wait for generation)
                metadata = extract_episode_metadata(slot.episode_path)
                bumper_path = find_existing_bumper(slot.show_label, metadata)

            if bumper_path:
                handle.write(bumper_path + "\n")
            handle.write(slot.episode_path + "\n")
            handle.flush()

            if (
                seed_threshold
                and not seed_announced
                and idx + 1 == seed_threshold
                and idx + 1 < len(rotated_slots)
            ):
                print(
                    f"[Playlist] Seeded first {seed_threshold} episodes without waiting for bumpers.",
                    flush=True,
                )
                if needed_bumpers:
                    print(
                        "[Playlist] Parallel bumper generation completed before writing remaining episodes.",
                        flush=True,
                    )
                seed_announced = True

            if idx < len(rotated_slots) - 1:
                # Collect bumpers for this block
                up_next = bumper_path if bumper_path else None
                sassy = SASSY_CARDS.draw_card()
                weather = None
                try:
                    weather_cfg = load_weather_config()
                    if weather_cfg.get("enabled", False):
                        weather_prob = weather_cfg.get("probability_between_episodes", 0.0)
                        if weather_prob > 0 and random.random() <= weather_prob:
                            weather = WEATHER_BUMPER_MARKER  # Will be rendered JIT
                except Exception:
                    pass
                
                # Queue for pre-generation with episode path
                block_generator = get_generator()
                next_episode = rotated_slots[idx + 1].episode_path if idx + 1 < len(rotated_slots) else None
                block_generator.queue_pregen({
                    "up_next_bumper": up_next,
                    "sassy_card": sassy,
                    "network_bumper": None,
                    "weather_bumper": weather,
                    "episode_path": next_episode,  # Store which episode this block is for
                })
                
                # Write bumper block marker - the streamer will use the pre-generated block
                handle.write(BUMPER_BLOCK_MARKER + "\n")


def write_episode_entry(handle, slot: EpisodeSlot, require_bumper: bool) -> None:
    """
    Write an episode entry to the playlist, optionally with a bumper.
    Always checks for existing bumpers, but only creates new ones if require_bumper=True.
    """
    bumper_path: Optional[str] = None
    metadata = extract_episode_metadata(slot.episode_path)

    # Always check for existing generic bumpers
    # NOTE: Specific-episode bumpers are generated dynamically (JIT), not saved as files
    try:
        bumper_path = find_existing_bumper(slot.show_label, None)  # Only check for generic

        # If no existing generic bumper found and require_bumper=True, try to create one
        if not bumper_path and require_bumper:
            bumper_path = ensure_bumper(slot.show_label, None)  # Only generate generic
    except Exception as exc:  # pragma: no cover - best effort
        if require_bumper:
            print(f"[Bumpers] Failed to render bumper for {slot.show_label}: {exc}")

    if bumper_path:
        handle.write(bumper_path + "\n")
    handle.write(slot.episode_path + "\n")
    handle.flush()


def maybe_write_network_bumper(handle) -> None:
    bumper = NETWORK_BUMPERS.draw_bumper()
    if bumper:
        handle.write(bumper + "\n")
        handle.flush()


def maybe_write_sassy_card(handle) -> None:
    card = SASSY_CARDS.draw_card()
    if card:
        handle.write(card + "\n")
        handle.flush()


def main():
    settings = load_settings()
    channel = resolve_channel(settings)
    # Default to /media/tvchannel (maps to /mnt/blackhole/media/tv on TrueNAS host)
    media_root = channel.get("media_root") or "/media/tvchannel"
    # Normalize path for container if needed
    media_root = _normalize_path_for_container(media_root)

    # Reset sassy card deck for fresh shuffle
    SASSY_CARDS.reset_deck()
    
    # Start bumper block pre-generation thread
    block_generator = get_generator()
    block_generator.start_pregen_thread()

    shows = filter_shows(channel)
    if not shows:
        print("[Playlist] No shows marked as included; playlist will be empty.")

    channel_mode = channel.get("playback_mode", "sequential")

    total_shows = len(shows)
    if total_shows:
        print(f"[Progress] Scanning {total_shows} shows from {media_root}", flush=True)

    entries = []
    for idx, show in enumerate(shows, start=1):
        show_label = show.get("label") or show.get("id") or "Untitled show"
        print(
            f"[Progress] [{idx}/{total_shows}] Collecting episodes for {show_label}",
            flush=True,
        )
        episodes = collect_show_episodes(media_root, show)
        if not episodes:
            continue
        show_mode = resolve_show_mode(
            channel_mode, show.get("playback_mode", "inherit")
        )
        ordered = order_episodes(episodes, show_mode)
        try:
            weight = float(show.get("weight", 1.0))
        except (TypeError, ValueError):
            weight = 1.0
        weight = max(0.1, weight)
        entries.append(
            {
                "config": show,
                "episodes": ordered,
                "weight": weight,
            }
        )

    if not entries:
        print("[Playlist] No playable episodes found.")
        open(PLAYLIST_FILE, "w", encoding="utf-8").close()
        return

    episode_slots = build_episode_schedule(
        entries, channel_mode, PLAYLIST_EPISODE_LIMIT
    )
    if not episode_slots:
        print("[Playlist] No episodes available after scheduling.")
        open(PLAYLIST_FILE, "w", encoding="utf-8").close()
        return

    print(
        f"[Progress] Scheduling {len(episode_slots)} episodes across {len(entries)} shows.",
        flush=True,
    )

    write_playlist_file(episode_slots)

    print(
        f"[Progress] Playlist ready. Seed size: {min(PLAYLIST_SEED_LIMIT, len(episode_slots))} episodes.",
        flush=True,
    )


if __name__ == "__main__":
    main()
