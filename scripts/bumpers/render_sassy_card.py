"""
Render minimalist "sassy card" bumpers for HBN.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIL import Image, ImageDraw, ImageFont

from scripts.music.add_music_to_bumper import add_random_music_to_bumper
from scripts.bumpers.ffmpeg_utils import run_ffmpeg, validate_video_file

DEFAULT_SASSY_CONFIG = "/app/config/sassy_messages.json"
DEFAULT_ASSETS_ROOT = "/app/assets"
DEFAULT_STYLE_KEY = "hbn-cozy"


@dataclass(frozen=True)
class CardStyle:
    name: str
    font_size: int
    text_color: tuple[int, int, int]
    text_align: str
    max_text_width_ratio: float
    vertical_anchor_ratio: float
    include_logo: bool
    add_music: bool
    background_mode: str  # "gradient" or "solid"
    bg_color_top: tuple[int, int, int]
    bg_color_bottom: tuple[int, int, int]


STYLE_PRESETS = {
    "hbn-cozy": CardStyle(
        name="hbn-cozy",
        font_size=52,
        text_color=(245, 245, 245),
        text_align="center",
        max_text_width_ratio=0.75,
        vertical_anchor_ratio=0.5,
        include_logo=True,
        add_music=True,
        background_mode="gradient",
        bg_color_top=(5, 5, 5),
        bg_color_bottom=(30, 30, 30),
    ),
    "adult-swim-minimal": CardStyle(
        name="adult-swim-minimal",
        font_size=48,
        text_color=(240, 240, 240),
        text_align="left",
        max_text_width_ratio=0.8,
        vertical_anchor_ratio=0.35,
        include_logo=False,
        add_music=False,
        background_mode="solid",
        bg_color_top=(0, 0, 0),
        bg_color_bottom=(0, 0, 0),
    ),
}


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

    repo_guess = (
        Path(__file__).resolve().parents[2]
        / "server"
        / "config"
        / "sassy_messages.json"
    )
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


def _is_hatemail(text: str) -> bool:
    """
    Detect if a message is hatemail (starts with quotes and ends with —Name pattern).
    """
    text = text.strip()
    # Check if it starts with a quote and contains an em dash or regular dash followed by text
    if text.startswith('"') and ("—" in text or " - " in text):
        return True
    return False


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """
    Load a font that supports Unicode characters like em dashes.
    Tries multiple common system fonts before falling back to default.
    """
    import platform

    system = platform.system()

    # List of fonts to try, in order of preference
    font_paths = []

    if system == "Darwin":  # macOS
        font_paths = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        ]
    elif system == "Linux":
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
        ]

    # Try common fallback paths
    font_paths.extend(
        [
            "DejaVuSans.ttf",
            "Arial.ttf",
        ]
    )

    for font_path in font_paths:
        try:
            font = ImageFont.truetype(font_path, size)
            # Test if font supports em dash by checking if it can measure it
            try:
                font.getbbox("—")
                return font
            except Exception:
                # Font loaded but might not support em dash, try next
                continue
        except (OSError, IOError):
            continue

    # Last resort: default font (may not support em dashes)
    return ImageFont.load_default()


def _normalize_text_for_font(text: str, font: ImageFont.ImageFont) -> str:
    """
    Normalize text to replace unsupported characters.
    Replaces em dashes with regular dashes if the font doesn't support them.
    """
    try:
        # Test if font supports em dash by checking if it can measure it properly
        bbox = font.getbbox("—")
        # Check if the bbox is valid (has non-zero width)
        if bbox and len(bbox) >= 4:
            width = bbox[2] - bbox[0]
            # If width is reasonable (not zero or extremely small), font likely supports it
            if width > 0:
                return text  # Font supports em dash, return as-is
    except Exception:
        pass

    # Font doesn't support em dash, replace with regular dash
    return text.replace("—", "-")


def _wrap_lines(
    text: str,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    """
    Wrap text into lines that fit within max_width.
    Improved version that handles punctuation and tries to break at natural points.
    """
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current: list[str] = []

    for word in words:
        current.append(word)
        candidate = " ".join(current)
        text_width = draw.textlength(candidate, font=font)
        
        if text_width > max_width:
            current.pop()  # Remove the word that made it too wide
            if current:
                # Try to break at a better point if we have punctuation
                line_text = " ".join(current)
                # Check if we can break at punctuation for better readability
                if len(current) > 1 and current[-1][-1] in ",;:.":
                    # Keep punctuation with previous word
                    lines.append(line_text)
                    current = [word]
                else:
                    # Break normally
                    lines.append(line_text)
                    current = [word]
            else:
                # Word itself is wider than max width; try to break it
                if len(word) > 20:  # Only break very long words
                    # Try to break at hyphens or other separators
                    if "-" in word:
                        parts = word.split("-", 1)
                        lines.append(parts[0] + "-")
                        current = [parts[1]] if parts[1] else []
                    else:
                        # Force break long word
                        lines.append(word[:20] + "-")
                        current = [word[20:]]
                else:
                    # Short word that's just too wide - keep it
                    lines.append(word)
                    current = []

    if current:
        lines.append(" ".join(current))

    return lines


def _calculate_optimal_font_size(
    text: str,
    width: int,
    height: int,
    style: CardStyle,
    min_size: int = 24,
    max_size: int = 200,
) -> int:
    """
    Calculate the optimal font size to fill the screen while keeping text readable.
    Uses binary search to find the largest font size that fits.
    """
    # Account for logo if present
    available_height = height
    if style.include_logo:
        available_height = int(height * 0.85)  # Reserve space for logo

    # Account for padding
    available_height = int(available_height * 0.9)  # 10% padding
    max_text_width = int(width * style.max_text_width_ratio)

    # Create a temporary image and draw context for measurements
    temp_img = Image.new("RGB", (width, height))
    temp_draw = ImageDraw.Draw(temp_img)

    best_size = min_size
    low, high = min_size, max_size

    while low <= high:
        mid = (low + high) // 2
        font = _load_font(mid)

        # Wrap text with this font size
        lines = _wrap_lines(text, temp_draw, font, max_text_width)

        if not lines:
            break

        # Calculate total height needed
        bbox = font.getbbox("Ag")
        line_height = bbox[3] - bbox[1]
        line_spacing = int(line_height * 0.3)  # 30% of line height for spacing
        total_text_height = (
            len(lines) * line_height + max(len(lines) - 1, 0) * line_spacing
        )

        # Check if it fits
        if total_text_height <= available_height:
            best_size = mid
            low = mid + 1  # Try larger
        else:
            high = mid - 1  # Too big, try smaller

    return best_size


def _draw_background(canvas: Image.Image, style: CardStyle) -> None:
    """
    Paint the card background according to the chosen style.
    """

    width, height = canvas.size
    base = Image.new("RGB", canvas.size, color=style.bg_color_top)

    if style.background_mode == "gradient":
        painter = ImageDraw.Draw(base)
        for y in range(height):
            ratio = y / max(1, height - 1)
            r = int(
                style.bg_color_top[0]
                + (style.bg_color_bottom[0] - style.bg_color_top[0]) * ratio
            )
            g = int(
                style.bg_color_top[1]
                + (style.bg_color_bottom[1] - style.bg_color_top[1]) * ratio
            )
            b = int(
                style.bg_color_top[2]
                + (style.bg_color_bottom[2] - style.bg_color_top[2]) * ratio
            )
            painter.line([(0, y), (width, y)], fill=(r, g, b))

    canvas.paste(base)


def _paste_logo(
    img: Image.Image,
    logo_path: Path,
    target_height: int = 90,
    margin: int = 36,
) -> None:
    if not logo_path.exists():
        print(f"[Warning] Logo file not found: {logo_path}", file=sys.stderr)
        return
    try:
        with Image.open(logo_path).convert("RGBA") as logo:
            w, h = logo.size
            if h == 0:
                print(f"[Warning] Logo has zero height: {logo_path}", file=sys.stderr)
                return
            scale = target_height / h
            resized = logo.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            img.paste(resized, (img.width - resized.width - margin, margin), resized)
    except OSError as e:
        print(f"[Warning] Failed to load logo {logo_path}: {e}", file=sys.stderr)
        return


def _resolve_style(config_style: str | None) -> CardStyle:
    """
    Map the style name from config into a CardStyle definition.
    """

    key = (config_style or DEFAULT_STYLE_KEY).lower()
    return STYLE_PRESETS.get(key, STYLE_PRESETS[DEFAULT_STYLE_KEY])


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

    style = _resolve_style(cfg.get("style"))
    assets_root = resolve_assets_root()
    if not logo_path:
        logo_candidate = assets_root / "branding" / "hbn_logo_bug.png"
        logo_path = str(logo_candidate) if logo_candidate.exists() else None

    # Calculate optimal font size to fill the screen
    # First load a test font to normalize text if needed
    test_font = _load_font(style.font_size)
    text = _normalize_text_for_font(text, test_font)

    font_size = _calculate_optimal_font_size(text, width, height, style)
    font = _load_font(font_size)

    with tempfile.TemporaryDirectory(prefix="sassy_card_") as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        frame_path = tmp_dir_path / "frame.png"

        img = Image.new("RGB", (width, height))
        _draw_background(img, style)

        # Validate that background was drawn (not all black unless style specifies black)
        # This is a basic check - if the image is completely black and style doesn't specify black, something went wrong
        if img.getextrema() == ((0, 0), (0, 0), (0, 0)):
            if style.bg_color_top != (0, 0, 0) or style.bg_color_bottom != (0, 0, 0):
                raise RuntimeError(
                    "Background drawing resulted in all-black image, but style doesn't specify black"
                )

        draw = ImageDraw.Draw(img)
        max_text_width = int(width * style.max_text_width_ratio)
        lines = _wrap_lines(text, draw, font, max_text_width)

        bbox = font.getbbox("Ag")
        line_height = bbox[3] - bbox[1]
        line_spacing = int(line_height * 0.3)  # 30% of line height for spacing
        total_text_height = (
            len(lines) * line_height + max(len(lines) - 1, 0) * line_spacing
        )

        if style.text_align == "left":
            x_pos = int(width * 0.08)
            y_start = int(height * style.vertical_anchor_ratio) - total_text_height // 2
        else:
            x_pos = None
            y_start = (height - total_text_height) // 2

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2]
            if style.text_align == "left":
                x = x_pos
            else:
                x = (width - line_width) // 2
            draw.text((x, y_start), line, font=font, fill=style.text_color)
            y_start += line_height + line_spacing

        if style.include_logo and logo_path:
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
        run_ffmpeg(
            video_cmd,
            timeout=60.0,
            description=f"Rendering sassy card video ({duration_sec}s)",
        )

        # Validate the generated video
        if not validate_video_file(silent_tmp, min_duration_sec=duration_sec * 0.9):
            raise RuntimeError(f"Generated video failed validation: {silent_tmp}")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not style.add_music:
            shutil.move(str(silent_tmp), str(output_path))
            # Final validation
            if not validate_video_file(
                output_path, min_duration_sec=duration_sec * 0.9
            ):
                raise RuntimeError(f"Final video failed validation: {output_path}")
        else:
            add_random_music_to_bumper(
                bumper_video_path=str(silent_tmp),
                output_path=str(output_path),
                music_volume=cfg.get("music_volume", 0.2),
            )
            # Final validation after music is added
            if not validate_video_file(
                output_path, min_duration_sec=duration_sec * 0.9
            ):
                raise RuntimeError(
                    f"Final video with music failed validation: {output_path}"
                )


if __name__ == "__main__":
    target = Path.cwd() / "sassy_preview.mp4"
    render_sassy_card(str(target))
    print(f"Rendered sassy card to {target}")
