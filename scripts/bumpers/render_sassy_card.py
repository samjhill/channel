"""
Render minimalist "sassy card" bumpers for HBN.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIL import Image, ImageDraw, ImageFont

from scripts.music.add_music_to_bumper import add_random_music_to_bumper

DEFAULT_SASSY_CONFIG = "/app/config/sassy_messages.json"
DEFAULT_ASSETS_ROOT = "/app/assets"


def resolve_assets_root() -> Path:
    override = os.environ.get("HBN_ASSETS_ROOT")
    if override:
        root = Path(override).expanduser()
        if root.exists():
            return root

    container_default = Path(DEFAULT_ASSETS_ROOT)
    if container_default.exists():
        return container_default

    repo_guess = Path(__file__).resolve().parents[2] / "assets"
    return repo_guess


def resolve_sassy_config_path() -> Path:
    override = os.environ.get("SASSY_CONFIG")
    if override:
        path = Path(override).expanduser()
        if path.exists():
            return path

    container_default = Path(DEFAULT_SASSY_CONFIG)
    if container_default.exists():
        return container_default

    repo_guess = Path(__file__).resolve().parents[2] / "server" / "config" / "sassy_messages.json"
    return repo_guess


def load_sassy_config() -> dict:
    path = resolve_sassy_config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"enabled": False}
    except json.JSONDecodeError as exc:
        print(f"[Sassy] Failed to parse config at {path}: {exc}")
        return {"enabled": False}


def pick_sassy_message(cfg: Optional[dict] = None) -> Optional[str]:
    cfg = cfg or load_sassy_config()
    if not cfg.get("enabled", True):
        return None
    messages = cfg.get("messages") or []
    if not messages:
        return None
    return random.choice(messages)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _wrap_lines(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current: list[str] = []

    for word in words:
        current.append(word)
        candidate = " ".join(current)
        if draw.textlength(candidate, font=font) > max_width:
            current.pop()
            if current:
                lines.append(" ".join(current))
                current = [word]
            else:
                # Word itself is wider than max width; force break.
                lines.append(word)
                current = []

    if current:
        lines.append(" ".join(current))

    return lines


def _draw_gradient_background(img: Image.Image) -> None:
    width, height = img.size
    base = Image.new("RGB", img.size, color=(5, 5, 5))
    draw = ImageDraw.Draw(base)
    top_color = (5, 5, 5)
    bottom_color = (30, 30, 30)
    for y in range(height):
        ratio = y / max(1, height - 1)
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    img.paste(base)


def _paste_logo(img: Image.Image, logo_path: Path, target_height: int = 90, margin: int = 36) -> None:
    if not logo_path.exists():
        return
    try:
        logo = Image.open(logo_path).convert("RGBA")
    except OSError:
        return

    w, h = logo.size
    if h == 0:
        return
    scale = target_height / h
    resized = logo.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    img.paste(resized, (img.width - resized.width - margin, margin), resized)


def render_sassy_card(
    output_path: str,
    width: int = 1600,
    height: int = 900,
    duration_sec: Optional[float] = None,
    fps: int = 30,
    logo_path: Optional[str] = None,
    message: Optional[str] = None,
) -> None:
    cfg = load_sassy_config()
    if not cfg.get("enabled", True):
        return

    text = message or pick_sassy_message(cfg)
    if not text:
        return

    if duration_sec is None:
        duration_sec = float(cfg.get("duration_seconds", 5))

    style = (cfg.get("style") or "hbn-cozy").lower()
    assets_root = resolve_assets_root()
    if not logo_path:
        logo_candidate = assets_root / "branding" / "hbn_logo_bug.png"
        logo_path = str(logo_candidate) if logo_candidate.exists() else None

    font = _load_font(52 if style != "adult-swim-minimal" else 48)

    with tempfile.TemporaryDirectory(prefix="sassy_card_") as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        frame_path = tmp_dir_path / "frame.png"

        if style == "adult-swim-minimal":
            img = Image.new("RGB", (width, height), color=(0, 0, 0))
        else:
            img = Image.new("RGB", (width, height))
            _draw_gradient_background(img)

        draw = ImageDraw.Draw(img)
        max_text_width = int(width * 0.75) if style != "adult-swim-minimal" else int(width * 0.8)
        lines = _wrap_lines(text, draw, font, max_text_width)

        bbox_height = font.getbbox("Ag")
        line_height = bbox_height[3] - bbox_height[1]
        total_text_height = len(lines) * line_height + max(len(lines) - 1, 0) * 12

        if style == "adult-swim-minimal":
            x_pos = int(width * 0.08)
            y_start = int(height * 0.35) - total_text_height // 2
        else:
            x_pos = None  # computed per line for centering
            y_start = (height - total_text_height) // 2

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2]
            if style == "adult-swim-minimal":
                x = x_pos
            else:
                x = (width - line_width) // 2
            draw.text((x, y_start), line, font=font, fill=(245, 245, 245))
            y_start += line_height + 12

        if style != "adult-swim-minimal" and logo_path:
            _paste_logo(img, Path(logo_path))

        img.save(frame_path)

        silent_tmp = tmp_dir_path / "silent.mp4"
        video_cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(frame_path),
            "-c:v",
            "libx264",
            "-t",
            str(duration_sec),
            "-r",
            str(fps),
            "-pix_fmt",
            "yuv420p",
            str(silent_tmp),
        ]
        subprocess.run(video_cmd, check=True)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if style == "adult-swim-minimal":
            shutil.move(str(silent_tmp), str(output_path))
        else:
            add_random_music_to_bumper(
                bumper_video_path=str(silent_tmp),
                output_path=str(output_path),
                music_volume=cfg.get("music_volume", 0.2),
            )


if __name__ == "__main__":
    target = Path.cwd() / "sassy_preview.mp4"
    render_sassy_card(str(target))
    print(f"Rendered sassy card to {target}")

