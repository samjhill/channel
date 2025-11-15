"""
Render full network branding bumpers for HBN with the complete logo.
"""

from __future__ import annotations

import math
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.music.add_music_to_bumper import add_random_music_to_bumper

# Brand palette
STEEL_BLUE = "#475D92"
ROSE_MAGENTA = "#DA5C86"
PAPER_WHITE = "#F8F5E9"
PEACH = "#FFB267"
NIGHT_INDIGO = "#090712"

LOGO_SVG_PATH = "branding/hbn_logo_bug.svg"
LOGO_PNG_PATH = "branding/hbn_logo_bug.png"


def resolve_assets_root() -> Path:
    override = os.environ.get("HBN_ASSETS_ROOT")
    if override:
        root = Path(override).expanduser()
        if root.exists():
            return root

    container_default = Path("/app/assets")
    if container_default.exists():
        return container_default

    repo_guess = Path(__file__).resolve().parents[2] / "assets"
    return repo_guess


def svg_to_png(svg_path: Path, output_path: Path, width: int = 1024, height: int = 1024) -> bool:
    """
    Convert SVG to PNG using available tools.
    Tries: rsvg-convert, cairosvg, inkscape, or falls back to existing PNG.
    """
    # First check if there's already a PNG version
    png_alt = svg_path.parent / f"{svg_path.stem}.png"
    if png_alt.exists():
        shutil.copy(png_alt, output_path)
        return True

    # Try rsvg-convert (librsvg)
    if shutil.which("rsvg-convert"):
        try:
            subprocess.run(
                ["rsvg-convert", "-w", str(width), "-h", str(height), "-o", str(output_path), str(svg_path)],
                check=True,
                capture_output=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    # Try cairosvg (Python package)
    try:
        import cairosvg
        cairosvg.svg2png(url=str(svg_path), write_to=str(output_path), output_width=width, output_height=height)
        return True
    except (ImportError, Exception):
        pass

    # Try inkscape
    if shutil.which("inkscape"):
        try:
            subprocess.run(
                ["inkscape", "--export-type=png", f"--export-filename={output_path}", f"--export-width={width}", f"--export-height={height}", str(svg_path)],
                check=True,
                capture_output=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    return False


def ensure_logo_png(logo_svg_path: Path, output_png_path: Path, size: int = 800) -> Optional[Path]:
    """Ensure we have a PNG version of the logo."""
    if output_png_path.exists():
        return output_png_path

    # First check if there's a PNG version already (preferred fallback)
    png_fallback = logo_svg_path.parent / f"{logo_svg_path.stem}.png"
    if png_fallback.exists() and png_fallback != logo_svg_path:
        # Resize the PNG if needed
        try:
            from PIL import Image
            img = Image.open(png_fallback)
            if img.size != (size, size):
                img = img.resize((size, size), Image.LANCZOS)
            img.save(output_png_path, "PNG")
            return output_png_path
        except Exception:
            shutil.copy(png_fallback, output_png_path)
            return output_png_path

    # Try to convert SVG if it exists
    if logo_svg_path.exists() and logo_svg_path.suffix.lower() == ".svg":
        if svg_to_png(logo_svg_path, output_png_path, width=size, height=size):
            return output_png_path

    return None


def clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(max_value, value))


def ease_out_cubic(x: float) -> float:
    x = clamp(x)
    return 1 - pow(1 - x, 3)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


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


def add_grain(
    image: Image.Image, opacity: float = 0.15, rng: Optional[np.random.Generator] = None
) -> Image.Image:
    if opacity <= 0:
        return image
    width, height = image.size
    noise_rng = rng or np.random.default_rng()
    noise = noise_rng.normal(loc=128, scale=30, size=(height, width)).astype(np.uint8)
    grain = Image.fromarray(noise, mode="L").convert("RGBA")
    alpha = int(255 * clamp(opacity))
    grain.putalpha(alpha)
    return Image.alpha_composite(image.convert("RGBA"), grain)


def load_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]
FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def render_network_brand_bumper(
    output_path: str,
    width: int = 1600,
    height: int = 900,
    duration_sec: float = 8.0,
    fps: int = 30,
    logo_svg_path: Optional[str] = None,
    seed: Optional[int] = None,
    music_volume: float = 0.4,
) -> None:
    """
    Render a network branding bumper with the full HBN logo.
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required but not found in PATH")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    assets_root = resolve_assets_root()

    if logo_svg_path is None:
        logo_svg_path = assets_root / LOGO_SVG_PATH
    else:
        logo_svg_path = Path(logo_svg_path)

    if seed is None:
        seed = secrets.randbits(32)
    rng = np.random.default_rng(seed)

    # Prepare logo
    with tempfile.TemporaryDirectory() as tmpdir:
        logo_png_tmp = Path(tmpdir) / "logo.png"
        logo_png = ensure_logo_png(logo_svg_path, logo_png_tmp, size=600)
        if not logo_png or not logo_png.exists():
            raise RuntimeError(f"Could not convert or find logo at {logo_svg_path}")

        base_logo = Image.open(logo_png).convert("RGBA")

        num_frames = int(duration_sec * fps)

        # Animation parameters
        logo_start = 0.2
        logo_fade_duration = 1.0
        logo_scale_anim_duration = 1.5
        text_start = 1.5
        text_fade_duration = 1.0
        fade_out_start = duration_sec - 1.5
        fade_out_duration = 1.5

        # Text to display
        network_name = "HILLSIDE BROADCASTING NETWORK"
        station_info = "W-HBN NEWARK · EST. 2025"

        # Load fonts
        title_font = load_font(FONT_CANDIDATES_BOLD, 72)
        subtitle_font = load_font(FONT_CANDIDATES_REGULAR, 32)

        # Generate frames
        for idx in range(num_frames):
            t = idx / fps

            # Background with subtle gradient
            frame = create_vertical_gradient(width, height, NIGHT_INDIGO, "#1a1520")
            frame = add_grain(frame, opacity=0.12, rng=rng)

            draw = ImageDraw.Draw(frame)

            center_x = width // 2

            # Logo animation - fade in and scale
            logo_progress = clamp((t - logo_start) / logo_fade_duration)
            logo_alpha = ease_out_cubic(logo_progress)
            logo_scale_progress = clamp((t - logo_start) / logo_scale_anim_duration)
            logo_scale = lerp(0.85, 1.0, ease_out_cubic(logo_scale_progress))

            if logo_alpha > 0:
                logo_size = (int(base_logo.width * logo_scale), int(base_logo.height * logo_scale))
                scaled_logo = base_logo.resize(logo_size, Image.LANCZOS)
                
                logo_layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                logo_alpha_mask = scaled_logo.getchannel("A").point(lambda a: int(a * logo_alpha))
                logo_with_alpha = scaled_logo.copy()
                logo_with_alpha.putalpha(logo_alpha_mask)
                
                logo_x = center_x - scaled_logo.width // 2
                logo_y = int(height * 0.35) - scaled_logo.height // 2
                logo_layer.paste(logo_with_alpha, (logo_x, logo_y), logo_with_alpha)
                frame = Image.alpha_composite(frame, logo_layer)
                draw = ImageDraw.Draw(frame)

            # Text animation - fade in below logo
            text_progress = clamp((t - text_start) / text_fade_duration)
            text_alpha = ease_out_cubic(text_progress)

            if text_alpha > 0:
                # Network name
                name_y = int(height * 0.6)
                name_fill = (*ImageColor.getrgb(PAPER_WHITE), int(255 * text_alpha))
                draw.text(
                    (center_x, name_y),
                    network_name,
                    font=title_font,
                    fill=name_fill,
                    anchor="mm",
                )

                # Station info
                info_y = name_y + 80
                info_fill = (*ImageColor.getrgb(PEACH), int(255 * text_alpha))
                draw.text(
                    (center_x, info_y),
                    station_info,
                    font=subtitle_font,
                    fill=info_fill,
                    anchor="mm",
                )

            # Fade out
            fade_progress = clamp((t - fade_out_start) / fade_out_duration) if t >= fade_out_start else 0.0
            if fade_progress > 0:
                fade_alpha = int(255 * fade_progress)
                black_layer = Image.new("RGBA", frame.size, (0, 0, 0, fade_alpha))
                frame = Image.alpha_composite(frame, black_layer)

            frame_path = Path(tmpdir) / f"frame_{idx:04d}.png"
            frame.convert("RGB").save(frame_path, "PNG")

        # Render video
        silent_video = Path(tmpdir) / "silent_bumper.mp4"
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(Path(tmpdir) / "frame_%04d.png"),
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(silent_video),
        ]
        subprocess.run(ffmpeg_cmd, check=True)

        # Add music
        add_random_music_to_bumper(
            str(silent_video),
            output_path,
            music_volume=music_volume,
        )


__all__ = ["render_network_brand_bumper"]

