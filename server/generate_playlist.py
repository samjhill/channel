#!/usr/bin/env python3

import os
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

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
from server.api.settings_service import load_settings

PLAYLIST_FILE = "/app/hls/playlist.txt"
DEFAULT_ASSETS_ROOT = "/app/assets"
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov")
SEASON_PATTERN = re.compile(r"(?:season|series)\s*\d+", re.IGNORECASE)
EPISODE_PATTERN = re.compile(r"S\d{1,2}E\d{1,2}.*$", re.IGNORECASE)


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


def ensure_bumper(show_title: str) -> str:
    os.makedirs(BUMPERS_DIR, exist_ok=True)
    bumper_path = os.path.join(BUMPERS_DIR, f"{safe_filename(show_title)}.mp4")
    if not os.path.exists(bumper_path):
        print(f"[Bumpers] Rendering 'Up Next' bumper for {show_title!r}")
        render_up_next_bumper(
            show_title=show_title,
            output_path=bumper_path,
            logo_path=os.path.join(ASSETS_ROOT, "branding", "hbn_logo_bug.png"),
        )
    return bumper_path


def resolve_assets_root() -> str:
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


ASSETS_ROOT = resolve_assets_root()
BUMPERS_DIR = os.path.join(ASSETS_ROOT, "bumpers", "up_next")
SASSY_BUMPERS_DIR = os.path.join(ASSETS_ROOT, "bumpers", "sassy")


def parse_include_overrides() -> set[str]:
    env_value = os.environ.get("INCLUDE_SHOWS", "")
    if not env_value.strip():
        return set()
    return {
        token.strip().lower()
        for token in env_value.split(",")
        if token.strip()
    }


ENV_INCLUDE_FILTER = parse_include_overrides()
SASSY_CONFIG: Optional[Dict[str, Any]] = None
SASSY_DECK: List[str] = []


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
    for root, _, files in os.walk(base_path):
        for fn in files:
            if not fn.lower().endswith(VIDEO_EXTENSIONS):
                continue
            episodes.append(os.path.join(root, fn))
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


def build_sequential_playlist(entries: Sequence[Dict[str, Any]]) -> List[str]:
    playlist: List[str] = []
    total_episodes = sum(len(entry["episodes"]) for entry in entries)
    processed = 0
    for entry in entries:
        show_label = entry["config"].get("label") or infer_show_title_from_path(
            entry["episodes"][0]
        )
        for episode in entry["episodes"]:
            processed += 1
            append_episode_with_bumper(playlist, show_label, episode)
            if processed < total_episodes:
                maybe_append_sassy_card(playlist)
    return playlist


def build_weighted_random_playlist(entries: Sequence[Dict[str, Any]]) -> List[str]:
    playlist: List[str] = []
    active = [
        {"config": entry["config"], "episodes": list(entry["episodes"]), "weight": entry["weight"]}
        for entry in entries
    ]
    total_episodes = sum(len(entry["episodes"]) for entry in entries)
    processed = 0

    while active:
        weights = [entry["weight"] for entry in active]
        chosen = random.choices(active, weights=weights, k=1)[0]
        if not chosen["episodes"]:
            active.remove(chosen)
            continue
        episode = chosen["episodes"].pop(0)
        if not chosen["episodes"]:
            active.remove(chosen)

        show_label = chosen["config"].get("label") or infer_show_title_from_path(episode)
        append_episode_with_bumper(playlist, show_label, episode)
        processed += 1
        if processed < total_episodes:
            maybe_append_sassy_card(playlist)

    return playlist


def append_episode_with_bumper(playlist: List[str], show_label: str, episode: str) -> None:
    try:
        bumper = ensure_bumper(show_label)
        playlist.append(bumper)
    except Exception as exc:  # pragma: no cover - best effort
        print(f"[Bumpers] Failed to render bumper for {show_label}: {exc}")
    playlist.append(episode)


def get_sassy_config() -> Dict[str, Any]:
    global SASSY_CONFIG
    if SASSY_CONFIG is None:
        SASSY_CONFIG = load_sassy_card_config()
    return SASSY_CONFIG


def ensure_sassy_cards(cfg: Dict[str, Any]) -> List[str]:
    os.makedirs(SASSY_BUMPERS_DIR, exist_ok=True)
    logo_candidate = os.path.join(ASSETS_ROOT, "branding", "hbn_logo_bug.png")
    logo_arg = logo_candidate if os.path.isfile(logo_candidate) else None

    cards: List[str] = []
    for idx, msg in enumerate(cfg.get("messages", []), start=1):
        slug = safe_filename(msg) or f"card_{idx}"
        destination = os.path.join(SASSY_BUMPERS_DIR, f"sassy_{slug}.mp4")
        if not os.path.exists(destination):
            try:
                render_sassy_card(
                    output_path=destination,
                    logo_path=logo_arg,
                    message=msg,
                )
            except Exception as exc:  # pragma: no cover
                print(f"[Sassy] Failed to render card for '{msg[:30]}': {exc}")
        if os.path.exists(destination):
            cards.append(destination)
    return cards


def draw_sassy_card_from_deck(cfg: Dict[str, Any]) -> Optional[str]:
    global SASSY_DECK
    if not SASSY_DECK:
        cards = ensure_sassy_cards(cfg)
        if not cards:
            return None
        SASSY_DECK = cards[:]
        random.shuffle(SASSY_DECK)
    return SASSY_DECK.pop() if SASSY_DECK else None


def maybe_generate_sassy_card() -> str | None:
    cfg = get_sassy_config()
    if not cfg.get("enabled", False):
        return None

    try:
        probability = float(cfg.get("probability_between_episodes", 0.0))
    except (TypeError, ValueError):
        probability = 0.0

    if probability <= 0 or random.random() > probability:
        return None

    card = draw_sassy_card_from_deck(cfg)
    return card


def maybe_append_sassy_card(playlist: List[str]) -> None:
    card = maybe_generate_sassy_card()
    if card:
        playlist.append(card)


def main():
    settings = load_settings()
    channel = resolve_channel(settings)
    media_root = channel.get("media_root") or "/media/tvchannel"

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
        show_mode = resolve_show_mode(channel_mode, show.get("playback_mode", "inherit"))
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

    if channel_mode == "random":
        playlist = build_weighted_random_playlist(entries)
    else:
        playlist = build_sequential_playlist(entries)

    print(
        f"[Progress] Playlist ready with {len(playlist)} entries "
        f"covering {len(entries)} shows.",
        flush=True,
    )

    os.makedirs(os.path.dirname(PLAYLIST_FILE), exist_ok=True)
    with open(PLAYLIST_FILE, "w", encoding="utf-8") as f:
        for entry in playlist:
            f.write(entry + "\n")


if __name__ == "__main__":
    main()

