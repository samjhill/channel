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
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, List, Tuple

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


def ease_in_out_cubic(x: float) -> float:
    x = clamp(x)
    if x < 0.5:
        return 4 * x * x * x
    return 1 - pow(-2 * x + 2, 3) / 2


def ease_in_cubic(x: float) -> float:
    x = clamp(x)
    return x * x * x


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


def parse_svg_elements(svg_path: Path) -> Tuple[ET.Element, List[Tuple[str, ET.Element]]]:
    """
    Parse SVG and return root element and list of animatable elements with their identifiers.
    Returns: (root_element, [(element_id, element), ...])
    
    Animation order:
    0. Large faded background HBN text
    1. Main HBN logo (in <g> with filter)
    2. Subheading "HILLSIDE BROADCASTING NETWORK"
    3. Call sign "W-HBN NEWARK · EST. 2025"
    4. Bottom accent line
    """
    tree = ET.parse(svg_path)
    root = tree.getroot()
    
    elements_to_animate = []
    rect_count = 0
    text_count = 0
    line_count = 0
    g_count = 0
    
    # Iterate through direct children and their children to find elements in order
    for elem in root:
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        
        # Skip defs
        if tag == 'defs':
            continue
            
        # Background rects (always visible, skip)
        if tag == 'rect':
            rect_count += 1
            continue
            
        # Large faded background HBN text (first text element)
        if tag == 'text' and text_count == 0:
            elements_to_animate.append(("bg_text", elem))
            text_count += 1
            continue
            
        # Main HBN logo in <g> with filter
        if tag == 'g':
            elements_to_animate.append(("main_logo", elem))
            g_count += 1
            continue
            
        # Subheading text
        if tag == 'text' and text_count == 1:
            elements_to_animate.append(("subheading", elem))
            text_count += 1
            continue
            
        # Call sign text
        if tag == 'text' and text_count == 2:
            elements_to_animate.append(("callsign", elem))
            text_count += 1
            continue
            
        # Bottom accent line
        if tag == 'line':
            elements_to_animate.append(("accent_line", elem))
            line_count += 1
            continue
    
    return root, elements_to_animate


def create_animated_svg(
    svg_path: Path,
    element_opacities: List[float],
    output_path: Path,
    width: int,
    height: int,
) -> None:
    """
    Create an animated SVG frame with specified opacities for each element.
    element_opacities should match the order returned by parse_svg_elements.
    """
    tree = ET.parse(svg_path)
    root = tree.getroot()
    
    # Set viewBox and dimensions
    root.set('width', str(width))
    root.set('height', str(height))
    root.set('viewBox', f"0 0 {width} {height}")
    
    # Track which element we're animating (same logic as parse_svg_elements)
    opacity_index = 0
    text_count = 0
    line_count = 0
    g_count = 0
    
    # Iterate through direct children
    for elem in root:
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        
        # Skip defs
        if tag == 'defs':
            continue
            
        # Background rects (always visible, skip)
        if tag == 'rect':
            continue
            
        # Large faded background HBN text (first text element)
        if tag == 'text' and text_count == 0:
            if opacity_index < len(element_opacities):
                opacity = element_opacities[opacity_index]
                existing_opacity = elem.get('opacity', '1.0')
                try:
                    existing_opacity = float(existing_opacity)
                except ValueError:
                    existing_opacity = 1.0
                final_opacity = existing_opacity * opacity
                elem.set('opacity', str(final_opacity))
                opacity_index += 1
            text_count += 1
            continue
            
        # Main HBN logo in <g> with filter
        if tag == 'g':
            if opacity_index < len(element_opacities):
                opacity = element_opacities[opacity_index]
                existing_opacity = elem.get('opacity', '1.0')
                try:
                    existing_opacity = float(existing_opacity)
                except ValueError:
                    existing_opacity = 1.0
                final_opacity = existing_opacity * opacity
                elem.set('opacity', str(final_opacity))
                opacity_index += 1
            g_count += 1
            continue
            
        # Subheading text
        if tag == 'text' and text_count == 1:
            if opacity_index < len(element_opacities):
                opacity = element_opacities[opacity_index]
                existing_opacity = elem.get('opacity', '1.0')
                try:
                    existing_opacity = float(existing_opacity)
                except ValueError:
                    existing_opacity = 1.0
                final_opacity = existing_opacity * opacity
                elem.set('opacity', str(final_opacity))
                opacity_index += 1
            text_count += 1
            continue
            
        # Call sign text
        if tag == 'text' and text_count == 2:
            if opacity_index < len(element_opacities):
                opacity = element_opacities[opacity_index]
                existing_opacity = elem.get('opacity', '1.0')
                try:
                    existing_opacity = float(existing_opacity)
                except ValueError:
                    existing_opacity = 1.0
                final_opacity = existing_opacity * opacity
                elem.set('opacity', str(final_opacity))
                opacity_index += 1
            text_count += 1
            continue
            
        # Bottom accent line
        if tag == 'line':
            if opacity_index < len(element_opacities):
                opacity = element_opacities[opacity_index]
                existing_opacity = elem.get('opacity', '1.0')
                try:
                    existing_opacity = float(existing_opacity)
                except ValueError:
                    existing_opacity = 1.0
                final_opacity = existing_opacity * opacity
                elem.set('opacity', str(final_opacity))
                opacity_index += 1
            line_count += 1
            continue
    
    # Write the modified SVG with proper namespace handling
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    tree.write(output_path, encoding='utf-8', xml_declaration=True)


def render_svg_to_png(
    svg_path: Path, output_path: Path, width: int, height: int
) -> bool:
    """
    Render SVG to PNG using available tools.
    """
    # Try rsvg-convert (librsvg) - best quality
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
    Uses SVG directly and animates each element separately for a professional look.
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

    if not logo_svg_path.exists():
        raise RuntimeError(f"Logo SVG not found at {logo_svg_path}")

    if seed is None:
        seed = secrets.randbits(32)
    rng = np.random.default_rng(seed)

    # Parse SVG to understand structure
    try:
        root, elements = parse_svg_elements(logo_svg_path)
        num_elements = len(elements)
        if num_elements == 0:
            raise RuntimeError("No animatable elements found in SVG")
    except Exception as e:
        raise RuntimeError(f"Failed to parse SVG: {e}") from e

    num_frames = int(duration_sec * fps)
    if num_frames == 0:
        raise RuntimeError(
            f"Invalid frame count: {num_frames} (duration={duration_sec}s, fps={fps})"
        )

    # Animation timing parameters (in seconds)
    animation_start = 0.3
    element_fade_duration = 0.8  # Duration for each element to fade in
    element_stagger = 0.15  # Delay between each element starting
    fade_out_start = duration_sec - 1.8
    fade_out_duration = 1.8

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Generate frames
        frames_generated = 0
        for idx in range(num_frames):
            t = idx / fps

            # Calculate opacity for each element
            element_opacities = []
            for i in range(num_elements):
                element_start = animation_start + (i * element_stagger)
                element_end = element_start + element_fade_duration
                
                if t < element_start:
                    # Not started yet
                    opacity = 0.0
                elif t < element_end:
                    # Fading in
                    progress = (t - element_start) / element_fade_duration
                    # Use ease-out for smooth fade-in
                    opacity = ease_out_cubic(progress)
                elif t < fade_out_start:
                    # Fully visible
                    opacity = 1.0
                else:
                    # Fading out
                    fade_progress = (t - fade_out_start) / fade_out_duration
                    fade_alpha = 1.0 - clamp(fade_progress)
                    opacity = fade_alpha
                
                element_opacities.append(opacity)

            # Create animated SVG frame
            animated_svg = tmpdir_path / f"frame_{idx:04d}.svg"
            create_animated_svg(
                logo_svg_path,
                element_opacities,
                animated_svg,
                width,
                height,
            )

            # Render SVG to PNG
            frame_png = tmpdir_path / f"frame_{idx:04d}.png"
            if not render_svg_to_png(animated_svg, frame_png, width, height):
                raise RuntimeError(
                    f"Failed to render SVG frame {idx}. "
                    "Ensure rsvg-convert, cairosvg, or inkscape is available."
                )

            # Load the rendered frame and add grain for texture
            try:
                frame = Image.open(frame_png).convert("RGBA")
                frame = add_grain(frame, opacity=0.10, rng=rng)

                # Save final frame
                frame.convert("RGB").save(frame_png, "PNG")
                
                # Validate frame is not all black (unless it's during fade out)
                if t < fade_out_start:
                    extrema = frame.getextrema()
                    if extrema == ((0, 0), (0, 0), (0, 0)):
                        raise RuntimeError(f"Frame {idx} is all black (time={t:.2f}s)")
            except Exception as e:
                raise RuntimeError(f"Failed to process frame {idx}: {e}") from e
            
            frames_generated += 1

        # Validate all frames were generated
        if frames_generated != num_frames:
            raise RuntimeError(
                f"Only generated {frames_generated} frames out of {num_frames} expected"
            )

        # Validate frame sequence
        if not validate_frame_sequence(tmpdir_path, num_frames, "frame_%04d.png"):
            raise RuntimeError("Frame sequence validation failed")

        # Render video
        silent_video = tmpdir_path / "silent_bumper.mp4"
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(tmpdir_path / "frame_%04d.png"),
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
