"""Render the HBN 'Up Next' bumper as an MP4 video."""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Iterable, Optional
import random
import secrets

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont

# Brand palette
STEEL_BLUE = "#475D92"
ROSE_MAGENTA = "#DA5C86"
PAPER_WHITE = "#F8F5E9"
PEACH = "#FFB267"

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


def add_grain(
    image: Image.Image, opacity: float = 0.25, noise_rng: Optional[np.random.Generator] = None
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

    grain_opacity = clamp(0.22 + rng.uniform(-0.06, 0.06), 0.08, 0.35)
    brightness_amp = 0.012 + rng.uniform(0, 0.012)
    brightness_freq = 0.25 + rng.uniform(-0.08, 0.1)
    brightness_phase = rng.uniform(0, 2 * math.pi)
    text_wiggle_amp = rng.uniform(0.0, 3.0)
    text_wiggle_freq = rng.uniform(0.3, 0.6)
    divider_width_factor = clamp(0.33 + rng.uniform(-0.04, 0.05), 0.25, 0.45)
    slide_base = 22 + rng.uniform(0, 12)
    logo_final_scale = 0.98 + rng.uniform(-0.02, 0.04)
    top_gradient = _adjust_color(STEEL_BLUE, rng.uniform(-0.05, 0.05))
    bottom_gradient = _adjust_color(ROSE_MAGENTA, rng.uniform(-0.05, 0.05))

    num_frames = int(duration_sec * fps)

    base_logo = Image.open(logo_path).convert("RGBA")
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
    title_font = compute_dynamic_font(
        draw_dummy,
        show_title_display,
        target_width=width * 0.72,
        base_size=80,
        min_size=42,
        font_candidates=FONT_CANDIDATES_BOLD,
    )

    logo_anim = AnimationWindow(start=0.0, duration=0.6)
    text_anim = AnimationWindow(start=0.2, duration=0.8)
    fade_out_anim = AnimationWindow(start=duration_sec - 0.6, duration=0.6)

    with tempfile.TemporaryDirectory() as tmpdir:
        for idx in range(num_frames):
            t = idx / fps

            frame = create_vertical_gradient(width, height, top_gradient, bottom_gradient)
            brightness_jitter = 1 + brightness_amp * math.sin(
                2 * math.pi * brightness_freq * t + brightness_phase
            )
            frame_np = (
                np.clip(
                    np.array(frame, dtype=np.float32) * brightness_jitter,
                    0,
                    255,
                ).astype(np.uint8)
            )
            frame = Image.fromarray(frame_np).convert("RGBA")
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
                wiggle = int(text_wiggle_amp * math.sin(2 * math.pi * text_wiggle_freq * t))
                up_next_y = int(height * 0.32) + slide_offset + wiggle
                divider_y = up_next_y + 120
                title_y = divider_y + 60

                upnext_fill = (*ImageColor.getrgb(PAPER_WHITE), int(255 * text_alpha))
                draw.text(
                    (center_x, up_next_y),
                    "UP NEXT",
                    font=upnext_font,
                    fill=upnext_fill,
                    anchor="mm",
                )

                divider_width = int(width * divider_width_factor)
                line_color = (*ImageColor.getrgb(PEACH), int(255 * text_alpha))
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
                draw.text(
                    (center_x, title_y),
                    show_title_display,
                    font=title_font,
                    fill=title_fill,
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
        subprocess.run(ffmpeg_cmd, check=True)


__all__ = ["render_up_next_bumper"]


