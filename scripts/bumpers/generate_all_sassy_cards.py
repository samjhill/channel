"""
Generate all sassy cards from the sassy_messages.json config.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.bumpers.render_sassy_card import load_sassy_config, render_sassy_card


def sanitize_filename(text: str, max_length: int = 100) -> str:
    """
    Convert a message text into a safe filename.
    """
    # Remove quotes and special characters
    text = text.replace('"', '').replace("'", "")
    # Replace em dashes and other special chars with hyphens
    text = text.replace("—", "-").replace(" - ", "-")
    # Remove or replace other problematic characters
    text = re.sub(r'[^\w\s-]', '', text)
    # Replace whitespace with underscores
    text = re.sub(r'\s+', '_', text)
    # Remove leading/trailing underscores
    text = text.strip('_')
    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length]
    return text.lower()


def generate_all_sassy_cards():
    """
    Generate video cards for all messages in the sassy config.
    """
    cfg = load_sassy_config()
    if not cfg.get("enabled", True):
        print("Sassy cards are disabled in config.")
        return

    messages = cfg.get("messages", [])
    if not messages:
        print("No messages found in config.")
        return

    # Determine output directory
    assets_root = REPO_ROOT / "assets"
    sassy_dir = assets_root / "bumpers" / "sassy"
    sassy_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating {len(messages)} sassy cards...")
    print(f"Output directory: {sassy_dir}")

    for i, message in enumerate(messages, 1):
        # Create a filename from the message
        filename = sanitize_filename(message)
        output_path = sassy_dir / f"{filename}.mp4"

        # Skip if already exists
        if output_path.exists():
            print(f"[{i}/{len(messages)}] Skipping (exists): {filename}.mp4")
            continue

        print(f"[{i}/{len(messages)}] Generating: {filename}.mp4")
        print(f"  Message: {message[:60]}...")

        try:
            render_sassy_card(
                output_path=str(output_path),
                message=message,
            )
            print(f"  ✓ Generated successfully")
        except Exception as e:
            print(f"  ✗ Error: {e}")
            continue

    print(f"\nDone! Generated cards are in {sassy_dir}")


if __name__ == "__main__":
    generate_all_sassy_cards()

