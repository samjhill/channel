"""Render the HBN 'Up Next' bumper as an MP4 video."""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
import random
import secrets

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.bumpers.ffmpeg_utils import (
    run_ffmpeg,
    validate_video_file,
    validate_frame_sequence,
)

# Brand palette
STEEL_BLUE = "#475D92"
ROSE_MAGENTA = "#DA5C86"
PAPER_WHITE = "#F8F5E9"
PEACH = "#FFB267"
GOLDENROD = "#F6C667"
NIGHT_INDIGO = "#1F2D50"
SEAFOAM = "#83F6C7"
CORAL = "#FF6F61"

THEME_PRESETS = [
    {
        "name": "sunset-glow",
        "top": STEEL_BLUE,
        "bottom": ROSE_MAGENTA,
        "accent": PEACH,
        "pattern": PAPER_WHITE,
    },
    {
        "name": "midnight-circuit",
        "top": NIGHT_INDIGO,
        "bottom": STEEL_BLUE,
        "accent": SEAFOAM,
        "pattern": "#9CC7FF",
    },
    {
        "name": "retro-warmth",
        "top": "#402A52",
        "bottom": CORAL,
        "accent": GOLDENROD,
        "pattern": "#FFD5C2",
    },
    {
        "name": "citrus-pop",
        "top": "#263238",
        "bottom": "#FBC02D",
        "accent": "#FF7043",
        "pattern": "#FFF8E1",
    },
    {
        "name": "ocean-depths",
        "top": "#0A1929",
        "bottom": "#1E3A5F",
        "accent": "#4FC3F7",
        "pattern": "#B2EBF2",
    },
    {
        "name": "forest-dawn",
        "top": "#1B4332",
        "bottom": "#40916C",
        "accent": "#95D5B2",
        "pattern": "#D8F3DC",
    },
    {
        "name": "purple-dream",
        "top": "#2D1B69",
        "bottom": "#6A4C93",
        "accent": "#C77DFF",
        "pattern": "#E0AAFF",
    },
    {
        "name": "amber-glow",
        "top": "#3E2723",
        "bottom": "#8D6E63",
        "accent": "#FFB74D",
        "pattern": "#FFE0B2",
    },
]

LOGO_DEFAULT_PATH = "assets/branding/hbn_logo_bug.png"


@dataclass(frozen=True)
class AnimationWindow:
    start: float
    duration: float

    def progress(self, t: float) -> float:
        if t <= self.start:
            return 0.0
        if t >= self.start + self.duration:
            return 1.0
        return (t - self.start) / self.duration


FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]
FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(max_value, value))


def ease_out_cubic(x: float) -> float:
    x = clamp(x)
    return 1 - pow(1 - x, 3)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def load_font(candidates: Iterable[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def create_vertical_gradient(
    width: int, height: int, top_color: str, bottom_color: str
) -> Image.Image:
    top_rgb = np.array(ImageColor.getrgb(top_color), dtype=np.float32)
    bottom_rgb = np.array(ImageColor.getrgb(bottom_color), dtype=np.float32)
    alpha = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
    gradient = top_rgb + (bottom_rgb - top_rgb) * alpha
    gradient = np.clip(gradient, 0, 255).astype(np.uint8)
    gradient = np.repeat(gradient, width, axis=1)
    return Image.fromarray(gradient, mode="RGB")


def _adjust_color(color: str, delta: float) -> str:
    rgb = np.array(ImageColor.getrgb(color), dtype=np.float32)
    rgb = np.clip(rgb * (1 + delta), 0, 255).astype(np.uint8)
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def choose_theme(rng: random.Random) -> dict:
    theme = rng.choice(THEME_PRESETS).copy()
    # Slightly perturb colors to keep things fresh
    theme["top"] = _adjust_color(theme["top"], rng.uniform(-0.08, 0.08))
    theme["bottom"] = _adjust_color(theme["bottom"], rng.uniform(-0.08, 0.08))
    theme["accent"] = _adjust_color(theme["accent"], rng.uniform(-0.06, 0.06))
    theme["pattern"] = _adjust_color(theme["pattern"], rng.uniform(-0.04, 0.04))
    return theme


def create_pattern_layer(
    width: int, height: int, color: str, opacity: float, rng: random.Random
) -> Image.Image:
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    alpha = int(255 * clamp(opacity, 0.02, 0.35))
    rgba = (*ImageColor.getrgb(color), alpha)

    pattern_type = rng.choice(["wavy", "dots", "diagonal"])
    spacing = rng.randint(40, 80)

    if pattern_type == "wavy":
        amplitude = rng.uniform(6, 14)
        frequency = rng.uniform(0.008, 0.014)
        for y in range(-spacing, height + spacing, spacing):
            points = []
            for x in range(-spacing, width + spacing, 8):
                offset = amplitude * math.sin((x * frequency) + (y * 0.05))
                points.append((x, y + offset))
            draw.line(points, fill=rgba, width=3)
    elif pattern_type == "dots":
        radius = rng.randint(6, 10)
        for y in range(0, height + spacing, spacing):
            for x in range(0, width + spacing, spacing):
                jitter_x = rng.uniform(-spacing * 0.2, spacing * 0.2)
                jitter_y = rng.uniform(-spacing * 0.2, spacing * 0.2)
                draw.ellipse(
                    (
                        x + jitter_x - radius,
                        y + jitter_y - radius,
                        x + jitter_x + radius,
                        y + jitter_y + radius,
                    ),
                    fill=rgba,
                    outline=None,
                )
    else:  # diagonal
        for offset in range(-height, width, spacing):
            draw.line(
                (
                    offset,
                    0,
                    offset + height,
                    height,
                ),
                fill=rgba,
                width=3,
            )
    return layer


def add_grain(
    image: Image.Image,
    opacity: float = 0.25,
    noise_rng: Optional[np.random.Generator] = None,
) -> Image.Image:
    if opacity <= 0:
        return image
    width, height = image.size
    rng = noise_rng or np.random.default_rng()
    noise = rng.normal(loc=128, scale=35, size=(height, width)).astype(np.uint8)
    grain = Image.fromarray(noise, mode="L").convert("RGBA")
    alpha = int(255 * clamp(opacity))
    grain.putalpha(alpha)
    return Image.alpha_composite(image.convert("RGBA"), grain)


def compute_dynamic_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    target_width: float,
    base_size: int,
    min_size: int,
    font_candidates: Iterable[str],
) -> ImageFont.FreeTypeFont:
    size = base_size
    while size >= min_size:
        font = load_font(font_candidates, size)
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        if width <= target_width:
            return font
        size -= 2
    return load_font(font_candidates, min_size)


def ensure_directory(path: str) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)


def render_up_next_bumper(
    show_title: str,
    output_path: str,
    width: int = 1600,
    height: int = 900,
    duration_sec: float = 6.0,
    fps: int = 30,
    logo_path: str = LOGO_DEFAULT_PATH,
    seed: Optional[int] = None,
    episode_label: Optional[str] = None,
) -> None:
    """
    Render a 6-second 'Up Next' bumper video for the given show_title.

    Saves it to output_path as an MP4 using ffmpeg.
    """

    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required but not found in PATH")

    ensure_directory(output_path)

    if seed is None:
        seed = secrets.randbits(32)
    rng = random.Random(seed)
    noise_rng = np.random.default_rng(rng.getrandbits(64))

    theme = choose_theme(rng)
    grain_opacity = clamp(0.22 + rng.uniform(-0.06, 0.06), 0.08, 0.35)
    brightness_amp = 0.012 + rng.uniform(0, 0.012)
    brightness_freq = 0.25 + rng.uniform(-0.08, 0.1)
    brightness_phase = rng.uniform(0, 2 * math.pi)
    text_wiggle_amp = rng.uniform(0.0, 3.0)
    text_wiggle_freq = rng.uniform(0.3, 0.6)
    divider_width_factor = clamp(0.33 + rng.uniform(-0.04, 0.05), 0.25, 0.45)
    slide_base = 22 + rng.uniform(0, 12)
    logo_final_scale = 0.98 + rng.uniform(-0.02, 0.04)
    top_gradient = theme["top"]
    bottom_gradient = theme["bottom"]
    pattern_layer_base = create_pattern_layer(
        width,
        height,
        theme["pattern"],
        opacity=0.12 + rng.uniform(-0.04, 0.04),
        rng=rng,
    )
    pattern_freq = rng.uniform(0.18, 0.35)
    pattern_phase = rng.uniform(0, 2 * math.pi)
    pattern_amp = rng.uniform(0.25, 0.45)

    num_frames = int(duration_sec * fps)
    if num_frames == 0:
        raise RuntimeError(
            f"Invalid frame count: {num_frames} (duration={duration_sec}s, fps={fps})"
        )

    try:
        base_logo = Image.open(logo_path).convert("RGBA")
        # Validate logo is not empty
        if base_logo.size[0] == 0 or base_logo.size[1] == 0:
            raise RuntimeError(f"Logo image has zero dimensions: {logo_path}")
        # Check if logo has any visible content (not completely transparent)
        # For RGBA images, check if alpha channel has any non-zero values
        if base_logo.mode == "RGBA":
            alpha_extrema = base_logo.getextrema()[3]
            if alpha_extrema == (0, 0):  # Alpha channel is all 0
                raise RuntimeError(f"Logo image is completely transparent: {logo_path}")
        # Check if RGB channels have any non-zero content (in case of RGB image)
        rgb_extrema = base_logo.getextrema()[:3]
        if all(ext == (0, 0) for ext in rgb_extrema):
            raise RuntimeError(f"Logo image appears to be all black: {logo_path}")
    except Exception as e:
        raise RuntimeError(f"Failed to load logo from {logo_path}: {e}") from e
    base_logo_width = 200
    scale = base_logo_width / base_logo.width
    base_logo = base_logo.resize(
        (int(base_logo.width * scale), int(base_logo.height * scale)),
        Image.LANCZOS,
    )

    upnext_font = load_font(FONT_CANDIDATES_BOLD, size=128)
    draw_dummy = ImageDraw.Draw(Image.new("RGB", (width, height)))
    show_title_clean = show_title.strip()
    show_title_display = show_title_clean.title()
    episode_label_display = (episode_label or "").strip()
    
    # Wrap long show titles to prevent overlap with subtitle
    # Calculate max characters per line based on target width (72% of screen width)
    max_title_width_px = width * 0.72
    # Estimate: fontsize 80, average char width ~40px, so ~30 chars per line
    # Use textwrap to wrap the title
    title_font_temp = load_font(FONT_CANDIDATES_BOLD, size=80)
    # Estimate character width (rough approximation)
    char_width_estimate = title_font_temp.getbbox("M")[2] - title_font_temp.getbbox("M")[0]
    max_chars_per_line = int(max_title_width_px / char_width_estimate) if char_width_estimate > 0 else 30
    show_title_wrapped = "\n".join(textwrap.wrap(show_title_display, width=max_chars_per_line, break_long_words=False, break_on_hyphens=False))
    
    title_font = compute_dynamic_font(
        draw_dummy,
        show_title_wrapped.split("\n")[0] if "\n" in show_title_wrapped else show_title_wrapped,  # Use first line for sizing
        target_width=width * 0.72,
        base_size=80,
        min_size=42,
        font_candidates=FONT_CANDIDATES_BOLD,
    )
    episode_font = None
    if episode_label_display:
        episode_font = compute_dynamic_font(
            draw_dummy,
            episode_label_display,
            target_width=width * 0.65,
            base_size=54,
            min_size=28,
            font_candidates=FONT_CANDIDATES_REGULAR,
        )

    logo_anim = AnimationWindow(start=0.0, duration=0.6)
    text_anim = AnimationWindow(start=0.2, duration=0.8)
    fade_out_anim = AnimationWindow(start=duration_sec - 0.6, duration=0.6)

    with tempfile.TemporaryDirectory() as tmpdir:
        frames_generated = 0
        for idx in range(num_frames):
            t = idx / fps

            frame = create_vertical_gradient(
                width, height, top_gradient, bottom_gradient
            )
            brightness_jitter = 1 + brightness_amp * math.sin(
                2 * math.pi * brightness_freq * t + brightness_phase
            )
            frame_np = np.clip(
                np.array(frame, dtype=np.float32) * brightness_jitter,
                0,
                255,
            ).astype(np.uint8)
            frame = Image.fromarray(frame_np).convert("RGBA")
            pattern_factor = clamp(
                0.6
                + pattern_amp
                * math.sin(2 * math.pi * pattern_freq * t + pattern_phase),
                0.1,
                1.0,
            )

            pattern_layer = pattern_layer_base.copy()
            alpha_channel = pattern_layer.split()[3].point(
                lambda a: int(clamp(a * pattern_factor, 0, 255))
            )
            pattern_layer.putalpha(alpha_channel)
            frame = Image.alpha_composite(frame, pattern_layer)
            frame = add_grain(frame, opacity=grain_opacity, noise_rng=noise_rng)
            draw = ImageDraw.Draw(frame)

            # Logo animation
            logo_progress = ease_out_cubic(logo_anim.progress(t))
            logo_scale = lerp(0.9, logo_final_scale, logo_progress)
            logo_alpha = logo_progress
            if logo_alpha > 0:
                scaled_logo = base_logo.resize(
                    (
                        int(base_logo.width * logo_scale),
                        int(base_logo.height * logo_scale),
                    ),
                    Image.LANCZOS,
                )
                logo_layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                resized = scaled_logo.copy()
                alpha_mask = resized.getchannel("A").point(
                    lambda a: int(a * logo_alpha)
                )
                resized.putalpha(alpha_mask)
                logo_layer.paste(resized, (40, 40), resized)
                frame = Image.alpha_composite(frame, logo_layer)
                draw = ImageDraw.Draw(frame)

            # Text animation
            text_progress = ease_out_cubic(text_anim.progress(t))
            text_alpha = clamp(text_progress)
            if text_alpha > 0:
                slide_offset = int((1 - text_alpha) * slide_base)
                center_x = width // 2
                wiggle = int(
                    text_wiggle_amp * math.sin(2 * math.pi * text_wiggle_freq * t)
                )
                up_next_y = int(height * 0.32) + slide_offset + wiggle
                divider_y = up_next_y + 120
                title_y = divider_y + 60
                
                # Calculate subtitle position based on title wrapping
                # Each wrapped line adds approximately fontsize + line spacing
                title_lines = show_title_wrapped.split("\n")
                line_height = title_font.size + 10  # Font size + line spacing
                title_height = len(title_lines) * line_height
                # Increase spacing to prevent overlap (96px base + extra for wrapped lines)
                subtitle_y = title_y + max(96, title_height + 20)

                upnext_fill = (*ImageColor.getrgb(PAPER_WHITE), int(255 * text_alpha))
                draw.text(
                    (center_x, up_next_y),
                    "UP NEXT",
                    font=upnext_font,
                    fill=upnext_fill,
                    anchor="mm",
                )

                divider_width = int(width * divider_width_factor)
                line_color = (
                    *ImageColor.getrgb(theme["accent"]),
                    int(255 * text_alpha),
                )
                draw.line(
                    (
                        center_x - divider_width // 2,
                        divider_y,
                        center_x + divider_width // 2,
                        divider_y,
                    ),
                    fill=line_color,
                    width=6,
                )

                title_fill = (
                    *ImageColor.getrgb(PAPER_WHITE if text_alpha > 0.5 else STEEL_BLUE),
                    int(255 * text_alpha),
                )
                # Use multiline_text for wrapped titles
                draw.multiline_text(
                    (center_x, title_y),
                    show_title_wrapped,
                    font=title_font,
                    fill=title_fill,
                    anchor="ma",  # Middle anchor for multiline
                    align="center",
                    spacing=10,  # Line spacing
                )
                if episode_label_display and episode_font:
                    subtitle_fill = (
                        *ImageColor.getrgb(PAPER_WHITE),
                        int(255 * text_alpha),
                    )
                    draw.text(
                        (center_x, subtitle_y),
                        episode_label_display,
                        font=episode_font,
                        fill=subtitle_fill,
                        anchor="ma",
                    )

            # Fade to black
            fade_amount = fade_out_anim.progress(t)
            if fade_amount > 0:
                fade_alpha = int(255 * fade_amount)
                black_layer = Image.new("RGBA", frame.size, (0, 0, 0, fade_alpha))
                frame = Image.alpha_composite(frame, black_layer)

            frame_path = os.path.join(tmpdir, f"frame_{idx:04d}.png")
            frame.convert("RGB").save(frame_path, "PNG")
            frames_generated += 1

            # Validate frame is not all black (unless it's during fade out)
            if t < fade_out_anim.start:
                extrema = frame.getextrema()
                if extrema == ((0, 0), (0, 0), (0, 0)):
                    raise RuntimeError(f"Frame {idx} is all black (time={t:.2f}s)")

        # Validate all frames were generated
        if frames_generated != num_frames:
            raise RuntimeError(
                f"Only generated {frames_generated} frames out of {num_frames} expected"
            )

        # Validate frame sequence
        if not validate_frame_sequence(Path(tmpdir), num_frames, "frame_%04d.png"):
            raise RuntimeError("Frame sequence validation failed")

        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            os.path.join(tmpdir, "frame_%04d.png"),
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            output_path,
        ]
        run_ffmpeg(
            ffmpeg_cmd,
            timeout=300.0,
            description=f"Rendering up next video ({duration_sec}s, {num_frames} frames)",
        )

        # Validate the generated video
        if not validate_video_file(
            Path(output_path), min_duration_sec=duration_sec * 0.9
        ):
            raise RuntimeError(f"Generated video failed validation: {output_path}")


__all__ = ["render_up_next_bumper"]
