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
NIGHT_INDIGO = "#090712"

LOGO_SVG_PATH = "branding/hbn_logo_full.svg"
LOGO_PNG_PATH = "branding/hbn_logo_full.png"


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


def svg_to_png(
    svg_path: Path, output_path: Path, width: int = 1024, height: int = 1024
) -> bool:
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
                [
                    "rsvg-convert",
                    "-w",
                    str(width),
                    "-h",
                    str(height),
                    "-o",
                    str(output_path),
                    str(svg_path),
                ],
                check=True,
                capture_output=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    # Try cairosvg (Python package)
    try:
        import cairosvg

        cairosvg.svg2png(
            url=str(svg_path),
            write_to=str(output_path),
            output_width=width,
            output_height=height,
        )
        return True
    except (ImportError, Exception):
        pass

    # Try inkscape
    if shutil.which("inkscape"):
        try:
            subprocess.run(
                [
                    "inkscape",
                    "--export-type=png",
                    f"--export-filename={output_path}",
                    f"--export-width={width}",
                    f"--export-height={height}",
                    str(svg_path),
                ],
                check=True,
                capture_output=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    return False


def ensure_logo_png(
    logo_svg_path: Path, output_png_path: Path, size: int = 800
) -> Optional[Path]:
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

    # Prepare full logo
    with tempfile.TemporaryDirectory() as tmpdir:
        logo_png_tmp = Path(tmpdir) / "logo_full.png"
        logo_png = ensure_logo_png(logo_svg_path, logo_png_tmp, size=max(width, height))
        if not logo_png or not logo_png.exists():
            raise RuntimeError(f"Could not convert or find logo at {logo_svg_path}")

        try:
            base_logo = Image.open(logo_png).convert("RGBA")
            # Validate logo is not empty
            if base_logo.size[0] == 0 or base_logo.size[1] == 0:
                raise RuntimeError(f"Logo image has zero dimensions: {logo_png}")
            # Check if logo has any visible content (not completely transparent)
            # For RGBA images, check if alpha channel has any non-zero values
            if base_logo.mode == "RGBA":
                alpha_extrema = base_logo.getextrema()[3]
                if alpha_extrema == (0, 0):  # Alpha channel is all 0
                    raise RuntimeError(
                        f"Logo image is completely transparent: {logo_png}"
                    )
            # Check if RGB channels have any non-zero content (in case of RGB image)
            rgb_extrema = base_logo.getextrema()[:3]
            if all(ext == (0, 0) for ext in rgb_extrema):
                raise RuntimeError(f"Logo image appears to be all black: {logo_png}")
        except Exception as e:
            raise RuntimeError(f"Failed to load logo from {logo_png}: {e}") from e

        num_frames = int(duration_sec * fps)
        if num_frames == 0:
            raise RuntimeError(
                f"Invalid frame count: {num_frames} (duration={duration_sec}s, fps={fps})"
            )

        # Animation parameters
        logo_start = 0.2
        logo_fade_duration = 1.0
        logo_scale_anim_duration = 1.5
        fade_out_start = duration_sec - 1.5
        fade_out_duration = 1.5

        # Generate frames
        frames_generated = 0
        for idx in range(num_frames):
            t = idx / fps

            # Start with the logo image as base (it already has the background and all text)
            frame = base_logo.copy().convert("RGBA")

            # Add subtle grain for texture
            frame = add_grain(frame, opacity=0.12, rng=rng)

            # Logo animation - fade in and scale
            logo_progress = clamp((t - logo_start) / logo_fade_duration)
            logo_alpha = ease_out_cubic(logo_progress)
            logo_scale_progress = clamp((t - logo_start) / logo_scale_anim_duration)
            logo_scale = lerp(0.92, 1.0, ease_out_cubic(logo_scale_progress))

            # Always create a canvas of the target dimensions and center the logo
            # Scale and apply alpha
            new_size = (int(frame.width * logo_scale), int(frame.height * logo_scale))
            scaled_frame = frame.resize(new_size, Image.LANCZOS)

            # Create centered canvas
            logo_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            logo_x = (width - scaled_frame.width) // 2
            logo_y = (height - scaled_frame.height) // 2

            # Apply alpha
            alpha_mask = scaled_frame.getchannel("A").point(
                lambda a: int(a * logo_alpha)
            )
            scaled_frame.putalpha(alpha_mask)

            logo_layer.paste(scaled_frame, (logo_x, logo_y), scaled_frame)
            frame = logo_layer

            # Fade out
            fade_progress = (
                clamp((t - fade_out_start) / fade_out_duration)
                if t >= fade_out_start
                else 0.0
            )
            if fade_progress > 0:
                fade_alpha = int(255 * fade_progress)
                black_layer = Image.new("RGBA", frame.size, (0, 0, 0, fade_alpha))
                frame = Image.alpha_composite(frame, black_layer)

            frame_path = Path(tmpdir) / f"frame_{idx:04d}.png"
            frame.convert("RGB").save(frame_path, "PNG")
            frames_generated += 1

            # Validate frame is not all black (unless it's during fade out)
            if t < fade_out_start:
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
        run_ffmpeg(
            ffmpeg_cmd,
            timeout=300.0,
            description=f"Rendering network brand video ({duration_sec}s, {num_frames} frames)",
        )

        # Validate the generated video
        if not validate_video_file(silent_video, min_duration_sec=duration_sec * 0.9):
            raise RuntimeError(f"Generated video failed validation: {silent_video}")

        # Add music
        add_random_music_to_bumper(
            str(silent_video),
            output_path,
            music_volume=music_volume,
        )

        # Final validation after music is added
        if not validate_video_file(
            Path(output_path), min_duration_sec=duration_sec * 0.9
        ):
            raise RuntimeError(
                f"Final video with music failed validation: {output_path}"
            )


__all__ = ["render_network_brand_bumper"]
