"""
Render weather bumper videos for HBN.
"""
from __future__ import annotations

import os
import math
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIL import Image, ImageDraw, ImageFont

from scripts.music.add_music_to_bumper import add_random_music_to_bumper
from scripts.bumpers.ffmpeg_utils import run_ffmpeg, validate_video_file
from server.services.weather_service import (
    get_current_weather,
    load_weather_config,
)

# Brand colors for gradient
STEEL_BLUE = (0x47, 0x5D, 0x92)
ROSE_MAGENTA = (0xDA, 0x5C, 0x86)
PAPER_WHITE = (0xF8, 0xF5, 0xE9)
PEACH = (0xEB, 0xA9, 0x83)


def resolve_assets_root() -> Path:
    """Resolve the assets root directory."""
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


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font, falling back to default if needed."""
    try:
        # Try common system fonts
        font_paths = [
            "/System/Library/Fonts/Helvetica.ttc",  # macOS
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",  # Linux alt
        ]
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    return ImageFont.truetype(font_path, size)
                except Exception:
                    continue
        # Fallback to default font
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def _make_gradient_bg(width: int, height: int) -> Image.Image:
    """Create a gradient background using HBN brand colors."""
    img = Image.new("RGB", (width, height))
    for y in range(height):
        t = y / (height - 1) if height > 1 else 0
        r = int(STEEL_BLUE[0] * (1 - t) + ROSE_MAGENTA[0] * t)
        g = int(STEEL_BLUE[1] * (1 - t) + ROSE_MAGENTA[1] * t)
        b = int(STEEL_BLUE[2] * (1 - t) + ROSE_MAGENTA[2] * t)
        for x in range(width):
            img.putpixel((x, y), (r, g, b))
    return img


def _paste_logo(
    img: Image.Image,
    logo_path: Path,
    target_height: int = 108,  # 12% of 900
    margin: int = 40,
) -> None:
    """Paste the HBN logo onto the image."""
    if not logo_path.exists():
        return
    try:
        logo_img = Image.open(logo_path).convert("RGBA")
        w, h = logo_img.size
        if h == 0:
            return
        scale = target_height / h
        resized = logo_img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        img.paste(resized, (margin, margin), resized)
    except Exception:
        pass


def _determine_weather_effect(condition: str) -> str:
    """Determine the visual weather effect based on condition text."""
    condition_lower = condition.lower()
    
    # Snow effects
    if any(word in condition_lower for word in ["snow", "blizzard", "sleet"]):
        return "snow"
    
    # Rain effects
    if any(word in condition_lower for word in ["rain", "drizzle", "shower", "storm", "thunderstorm"]):
        return "rain"
    
    # Fog/mist
    if any(word in condition_lower for word in ["fog", "mist", "haze"]):
        return "fog"
    
    # Clear/sunny
    if any(word in condition_lower for word in ["clear", "sunny", "sun"]):
        return "sun"
    
    # Cloudy
    if any(word in condition_lower for word in ["cloud", "overcast"]):
        return "clouds"
    
    # Default to clouds for unknown conditions
    return "clouds"


def _draw_snowflakes(
    img: Image.Image,
    width: int,
    height: int,
    frame_num: int,
    fps: float,
    intensity: float = 1.0,
) -> None:
    """Draw animated snowflakes falling from top to bottom."""
    num_flakes = int(80 * intensity)  # More flakes for heavier snow
    snow_speed = 2.0  # Pixels per frame
    flake_size = 3
    
    # Create a separate layer for snowflakes
    snow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    snow_draw = ImageDraw.Draw(snow_layer)
    
    for i in range(num_flakes):
        # Create consistent position for each flake using seed
        seed = (frame_num * 1000 + i) % 1000000
        random.seed(seed)
        
        # X position stays consistent per flake
        x = (i * 7919 + seed * 337) % width  # Pseudo-random but consistent
        
        # Y position moves down with frame
        y = (frame_num * snow_speed + i * 47) % (height + 200) - 100
        
        # Only draw if on screen
        if 0 <= y <= height:
            # Add some horizontal drift
            drift = math.sin((frame_num + i) * 0.1) * 2
            x += int(drift)
            
            # Draw snowflake (simple white circle/star)
            flake_alpha = int(180 + 75 * math.sin(frame_num * 0.2 + i))
            flake_alpha = max(100, min(255, flake_alpha))
            
            # Draw main flake body (white with alpha)
            snow_draw.ellipse(
                [x - flake_size, y - flake_size, x + flake_size, y + flake_size],
                fill=(255, 255, 255, flake_alpha),
            )
            
            # Add sparkle effect (cross pattern)
            if frame_num % 3 == 0:
                for offset in [(3, 0), (-3, 0), (0, 3), (0, -3)]:
                    snow_draw.ellipse(
                        [
                            x + offset[0] - 1,
                            y + offset[1] - 1,
                            x + offset[0] + 1,
                            y + offset[1] + 1,
                        ],
                        fill=(255, 255, 255, flake_alpha // 2),
                    )
    
    # Composite snow layer onto image
    img.alpha_composite(snow_layer)


def _draw_raindrops(
    img: Image.Image,
    width: int,
    height: int,
    frame_num: int,
    fps: float,
    intensity: float = 1.0,
) -> None:
    """Draw animated raindrops falling from top to bottom."""
    num_drops = int(150 * intensity)  # More drops for heavier rain
    rain_speed = 8.0  # Pixels per frame (rain falls faster than snow)
    
    # Create a separate layer for raindrops
    rain_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    rain_draw = ImageDraw.Draw(rain_layer)
    
    for i in range(num_drops):
        seed = (frame_num * 1000 + i) % 1000000
        random.seed(seed)
        
        # X position
        x = (i * 7919 + seed * 337) % width
        
        # Y position moves down
        y = (frame_num * rain_speed + i * 73) % (height + 300) - 150
        
        if 0 <= y <= height:
            # Raindrops are thin vertical lines
            drop_length = random.randint(12, 25)
            drop_width = 2
            
            # Add slight angle (rain falls at an angle)
            angle = random.uniform(-0.15, 0.05)
            end_x = x + math.sin(angle) * drop_length
            end_y = y + math.cos(angle) * drop_length
            
            # Draw raindrop as line (light blue with transparency)
            drop_alpha = 200
            rain_draw.line(
                [(x, y), (end_x, end_y)],
                fill=(200, 220, 255, drop_alpha),
                width=drop_width,
            )
            
            # Add highlight on top of drop
            if frame_num % 2 == 0:
                rain_draw.ellipse(
                    [x - 1, y - 1, x + 1, y + 1],
                    fill=(255, 255, 255, 180),
                )
    
    # Composite rain layer onto image
    img.alpha_composite(rain_layer)


def _draw_fog(
    img: Image.Image,
    width: int,
    height: int,
    frame_num: int,
    fps: float,
    intensity: float = 1.0,
) -> None:
    """Draw animated fog effect."""
    # Fog is represented as semi-transparent white/gray layers
    num_layers = 3
    
    # Create a separate layer for fog
    fog_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    fog_draw = ImageDraw.Draw(fog_layer)
    
    for layer in range(num_layers):
        layer_speed = 0.5 + layer * 0.3
        offset = int((frame_num * layer_speed) % (width + 200)) - 100
        
        # Draw wavy fog bands
        for y_pos in range(0, height, 40):
            wave_x = offset + int(math.sin(y_pos * 0.01 + frame_num * 0.1) * 150)
            alpha = int(40 * intensity * (1 - layer * 0.3))
            
            # Draw soft circular fog patches
            for patch_x in range(wave_x, width + 200, 250):
                for patch_y in range(y_pos, min(y_pos + 40, height), 40):
                    size = 100 + layer * 25
                    fog_draw.ellipse(
                        [
                            patch_x - size,
                            patch_y - size,
                            patch_x + size,
                            patch_y + size,
                        ],
                        fill=(240, 240, 245, alpha),
                    )
    
    # Composite fog layer onto image
    img.alpha_composite(fog_layer)


def _draw_sun_rays(
    img: Image.Image,
    width: int,
    height: int,
    frame_num: int,
    fps: float,
) -> None:
    """Draw animated sun rays."""
    center_x = int(width * 0.75)
    center_y = int(height * 0.25)
    num_rays = 12
    
    # Create a separate layer for sun
    sun_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sun_draw = ImageDraw.Draw(sun_layer)
    
    # Animate ray rotation
    rotation = (frame_num * 0.5) % 360
    
    # Draw sun rays
    for i in range(num_rays):
        angle = (i * 360 / num_rays + rotation) * math.pi / 180
        ray_length = 150
        
        # Draw sun ray (gradient-like effect with multiple segments)
        base_alpha = int(100 + 50 * math.sin(frame_num * 0.1 + i))
        for dist in range(0, int(ray_length), 8):
            fade = 1 - (dist / ray_length)
            ray_alpha = int(base_alpha * fade)
            x = int(center_x + math.cos(angle) * dist)
            y = int(center_y + math.sin(angle) * dist)
            size = int(4 * fade)
            if size > 0:
                sun_draw.ellipse(
                    [x - size, y - size, x + size, y + size],
                    fill=(255, 255, 200, ray_alpha),
                )
    
    # Draw sun center (bright yellow)
    sun_radius = 60
    sun_alpha = int(200 + 40 * math.sin(frame_num * 0.15))
    sun_draw.ellipse(
        [
            center_x - sun_radius,
            center_y - sun_radius,
            center_x + sun_radius,
            center_y + sun_radius,
        ],
        fill=(255, 255, 150, sun_alpha),
    )
    
    # Composite sun layer onto image
    img.alpha_composite(sun_layer)


def _draw_clouds(
    img: Image.Image,
    width: int,
    height: int,
    frame_num: int,
    fps: float,
) -> None:
    """Draw animated cloud layers."""
    num_clouds = 5
    
    # Create a separate layer for clouds
    cloud_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    cloud_draw = ImageDraw.Draw(cloud_layer)
    
    for i in range(num_clouds):
        cloud_speed = 0.3 + i * 0.1
        offset = int((frame_num * cloud_speed) % (width + 400)) - 200
        y_pos = int(height * (0.2 + i * 0.15))
        
        # Draw cloud as overlapping circles (puffy cloud effect)
        cloud_x = offset + i * 180
        cloud_alpha = 140
        cloud_size = 70 + i * 15
        
        # Draw cloud with multiple overlapping circles
        circles = [
            (cloud_x, y_pos, cloud_size),
            (cloud_x + 50, y_pos - 15, cloud_size - 10),
            (cloud_x + 100, y_pos, cloud_size - 5),
            (cloud_x + 25, y_pos + 15, cloud_size - 15),
            (cloud_x + 75, y_pos + 10, cloud_size - 20),
        ]
        
        for cx, cy, size in circles:
            # Add subtle vertical movement
            drift_y = int(math.sin(frame_num * 0.05 + i * 0.5) * 8)
            cloud_draw.ellipse(
                [
                    cx - size,
                    cy + drift_y - size // 2,
                    cx + size,
                    cy + drift_y + size // 2,
                ],
                fill=(200, 200, 220, cloud_alpha),
            )
    
    # Composite cloud layer onto image
    img.alpha_composite(cloud_layer)


def get_weather_background_path(effect_type: str) -> Optional[Path]:
    """Get the path to a pre-generated weather background video."""
    assets_root = resolve_assets_root()
    bg_path = assets_root / "bumpers" / "weather" / f"bg_{effect_type}.mp4"
    return bg_path if bg_path.exists() else None


def render_weather_bumper_fast(
    output_path: str,
    weather,
    cfg: dict,
    width: int = 1600,
    height: int = 900,
    fps: int = 30,
) -> bool:
    """
    Fast weather bumper renderer using pre-generated backgrounds and ffmpeg text overlay.
    
    This is much faster than rendering frames - just overlays text on a background video.
    """
    effect_type = _determine_weather_effect(weather.condition)
    bg_path = get_weather_background_path(effect_type)
    
    if not bg_path:
        # Fallback: generate on-the-fly if background doesn't exist
        print(f"[Weather] Background not found for {effect_type}, falling back to frame-by-frame render")
        return render_weather_bumper(output_path, width, height, fps, None, False, use_fast_render=False)
    
    duration_sec = cfg.get("duration_seconds", 5)
    temp_unit = "°F" if cfg.get("units", "imperial") == "imperial" else "°C"
    location_line = f"{weather.city}, {weather.region}"
    temp_line = f"{round(weather.temperature)}{temp_unit} – {weather.condition}"
    feels_line = f"Feels like {round(weather.feels_like)}{temp_unit}"
    
    with tempfile.TemporaryDirectory(prefix="weather_fast_") as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        silent_output = tmp_dir_path / "silent.mp4"
        
        # Build ffmpeg filter for text overlays
        # Escape text for ffmpeg
        def escape_text(text: str) -> str:
            return text.replace(":", "\\:").replace("'", "\\'").replace("[", "\\[").replace("]", "\\]")
        
        # Font path (we'll try to use a system font)
        font_path = "/System/Library/Fonts/Helvetica.ttc" if os.path.exists("/System/Library/Fonts/Helvetica.ttc") else ""
        
        # Build text overlay filter
        filter_parts = []
        
        # Title
        title_y = int(height * 0.18)
        filter_parts.append(
            f"drawtext=text='CURRENT WEATHER':"
            f"fontfile={font_path if font_path else 'Arial'}:"
            f"fontsize=48:"
            f"fontcolor=0xF8F5E9:"
            f"x=(w-text_w)/2:"
            f"y={title_y}:"
            f"box=0:boxborderw=0"
        )
        
        # Location
        location_y = int(height * 0.30)
        filter_parts.append(
            f"drawtext=text='{escape_text(location_line)}':"
            f"fontfile={font_path if font_path else 'Arial'}:"
            f"fontsize=40:"
            f"fontcolor=0xF8F5E9:"
            f"x=(w-text_w)/2:"
            f"y={location_y}:"
            f"box=0:boxborderw=0"
        )
        
        # Temperature and condition
        temp_y = int(height * 0.45)
        filter_parts.append(
            f"drawtext=text='{escape_text(temp_line)}':"
            f"fontfile={font_path if font_path else 'Arial'}:"
            f"fontsize=40:"
            f"fontcolor=0xF8F5E9:"
            f"x=(w-text_w)/2:"
            f"y={temp_y}:"
            f"box=0:boxborderw=0"
        )
        
        # Feels like
        feels_y = int(height * 0.57)
        filter_parts.append(
            f"drawtext=text='{escape_text(feels_line)}':"
            f"fontfile={font_path if font_path else 'Arial'}:"
            f"fontsize=28:"
            f"fontcolor=0xEBA983:"
            f"x=(w-text_w)/2:"
            f"y={feels_y}:"
            f"box=0:boxborderw=0"
        )
        
        filter_complex = ",".join(filter_parts)
        
        # Use ffmpeg to overlay text on background video
        video_cmd = [
            "ffmpeg",
            "-y",
            "-stream_loop", "-1",  # Loop the background video infinitely
            "-i",
            str(bg_path),
            "-vf",
            filter_complex,
            "-t",
            str(duration_sec),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",  # Faster preset for quick rendering
            "-crf",
            "23",  # Slightly lower quality for speed
            "-pix_fmt",
            "yuv420p",
            "-an",  # No audio yet
            str(silent_output),
        ]
        
        try:
            print(f"[Weather] Fast render: overlaying text on {effect_type} background...")
            run_ffmpeg(
                video_cmd,
                timeout=30.0,
                description=f"Overlaying text on {effect_type} background",
            )
        except Exception as e:
            print(f"[Weather] Fast render failed: {e}, falling back to frame-by-frame", file=sys.stderr)
            # Fallback to frame-by-frame with fast render disabled to avoid recursion
            return render_weather_bumper(output_path, width, height, fps, None, False, use_fast_render=False)
        
        # Add music
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            add_random_music_to_bumper(
                bumper_video_path=str(silent_output),
                output_path=str(output_path_obj),
                music_volume=cfg.get("music_volume", 0.2),
            )
            return output_path_obj.exists()
        except Exception as e:
            print(f"[Weather] Failed to add music: {e}", file=sys.stderr)
            import shutil
            shutil.copy(str(silent_output), str(output_path_obj))
            return output_path_obj.exists()


def render_weather_bumper(
    output_path: str,
    width: int = 1600,
    height: int = 900,
    fps: int = 30,
    logo_path: Optional[str] = None,
    test_mode: bool = False,
    use_fast_render: bool = True,
) -> bool:
    """
    Render a weather bumper MP4 to output_path.
    
    Args:
        output_path: Path where the rendered video should be saved
        width: Video width in pixels
        height: Video height in pixels
        fps: Frames per second
        logo_path: Optional path to logo image
        test_mode: If True, use mock weather data instead of fetching from API
    
    Returns True if a bumper was created, False otherwise (e.g. no weather data).
    """
    cfg = load_weather_config()
    if not cfg.get("enabled", True) and not test_mode:
        return False
    
    if test_mode:
        # Use mock weather data for testing
        from dataclasses import dataclass
        weather = type('WeatherInfo', (), {
            'temperature': 72.5,
            'feels_like': 70.0,
            'condition': 'Partly Cloudy',
            'city': cfg.get('location', {}).get('city', 'Newark'),
            'region': cfg.get('location', {}).get('region', 'NJ'),
            'country': cfg.get('location', {}).get('country', 'US'),
        })()
    else:
        weather = get_current_weather()
        if weather is None:
            api_var = cfg.get("api_key_env_var", "HBN_WEATHER_API_KEY")
            print(
                f"[Weather] Weather bumpers are enabled but no weather data is available. "
                f"Set the {api_var} environment variable with your API key to enable weather bumpers.",
                file=sys.stderr,
            )
            return False
    
    # Try fast render first (uses pre-generated backgrounds)
    if use_fast_render:
        try:
            return render_weather_bumper_fast(output_path, weather, cfg, width, height, fps)
        except Exception as e:
            print(f"[Weather] Fast render failed: {e}, using frame-by-frame fallback", file=sys.stderr)
            # Continue to frame-by-frame rendering below
    
    # Frame-by-frame rendering (fallback or if fast render disabled)
    duration_sec = cfg.get("duration_seconds", 5)
    
    # Resolve logo path
    assets_root = resolve_assets_root()
    if not logo_path:
        logo_candidate = assets_root / "branding" / "hbn_logo_bug.png"
        logo_path = str(logo_candidate) if logo_candidate.exists() else None
    
    # Load fonts
    font_title = _load_font(48)
    font_main = _load_font(40)
    font_small = _load_font(28)
    
    # Prepare text strings
    temp_unit = "°F" if cfg.get("units", "imperial") == "imperial" else "°C"
    location_line = f"{weather.city}, {weather.region}"
    temp_line = f"{round(weather.temperature)}{temp_unit} – {weather.condition}"
    feels_line = f"Feels like {round(weather.feels_like)}{temp_unit}"
    
    # Determine weather effect type
    effect_type = _determine_weather_effect(weather.condition)
    
    # Calculate intensity based on condition (heavier descriptions = more intense)
    condition_lower = weather.condition.lower()
    intensity = 1.0
    if any(word in condition_lower for word in ["heavy", "intense", "severe", "extreme"]):
        intensity = 1.5
    elif any(word in condition_lower for word in ["light", "slight", "scattered"]):
        intensity = 0.6
    
    # Generate all frames for animation
    total_frames = int(duration_sec * fps)
    
    with tempfile.TemporaryDirectory(prefix="weather_bumper_") as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        
        print(f"[Weather] Rendering {total_frames} frames with {effect_type} effect...")
        
        # Generate each frame
        for frame_num in range(total_frames):
            # Create base gradient background
            img = _make_gradient_bg(width, height)
            
            # Convert to RGBA for transparency support in effects
            img = img.convert("RGBA")
            draw = ImageDraw.Draw(img)
            
            # Draw weather effects first (behind text)
            if effect_type == "snow":
                _draw_snowflakes(img, width, height, frame_num, fps, intensity)
            elif effect_type == "rain":
                _draw_raindrops(img, width, height, frame_num, fps, intensity)
            elif effect_type == "fog":
                _draw_fog(img, width, height, frame_num, fps, intensity)
            elif effect_type == "sun":
                _draw_sun_rays(img, width, height, frame_num, fps)
            elif effect_type == "clouds":
                _draw_clouds(img, width, height, frame_num, fps)
            
            # Convert back to RGB for text rendering (more efficient, compositing is done)
            img = img.convert("RGB")
            draw = ImageDraw.Draw(img)
            
            # Draw title
            title = "CURRENT WEATHER"
            bbox = draw.textbbox((0, 0), title, font=font_title)
            title_w = bbox[2] - bbox[0]
            draw.text(
                ((width - title_w) / 2, height * 0.18),
                title,
                font=font_title,
                fill=PAPER_WHITE,
            )
            
            # Draw location
            bbox = draw.textbbox((0, 0), location_line, font=font_main)
            location_w = bbox[2] - bbox[0]
            draw.text(
                ((width - location_w) / 2, height * 0.30),
                location_line,
                font=font_main,
                fill=PAPER_WHITE,
            )
            
            # Draw temperature and condition
            bbox = draw.textbbox((0, 0), temp_line, font=font_main)
            temp_w = bbox[2] - bbox[0]
            draw.text(
                ((width - temp_w) / 2, height * 0.45),
                temp_line,
                font=font_main,
                fill=PAPER_WHITE,
            )
            
            # Draw feels like
            bbox = draw.textbbox((0, 0), feels_line, font=font_small)
            feels_w = bbox[2] - bbox[0]
            draw.text(
                ((width - feels_w) / 2, height * 0.57),
                feels_line,
                font=font_small,
                fill=PEACH,
            )
            
            # Add logo
            if logo_path:
                _paste_logo(img, Path(logo_path))
            
            # Save frame
            frame_path = tmp_dir_path / f"frame_{frame_num:04d}.png"
            img.save(frame_path)
            
            # Progress indicator
            if (frame_num + 1) % 30 == 0 or frame_num == total_frames - 1:
                progress = int(100 * (frame_num + 1) / total_frames)
                print(f"[Weather] Progress: {progress}% ({frame_num + 1}/{total_frames} frames)")
        
        # Encode animated video from frame sequence
        silent_video = tmp_dir_path / "weather_silent.mp4"
        video_cmd = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(tmp_dir_path / "frame_%04d.png"),
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            str(silent_video),
        ]
        
        try:
            run_ffmpeg(
                video_cmd,
                timeout=60.0,
                description=f"Rendering weather bumper video ({duration_sec}s)",
            )
        except Exception as e:
            print(f"[Weather] Failed to render video: {e}", file=sys.stderr)
            return False
        
        # Validate the generated video
        if not validate_video_file(silent_video, min_duration_sec=duration_sec * 0.9):
            print("[Weather] Generated video failed validation", file=sys.stderr)
            return False
        
        # Add low-volume music (optional, but recommended)
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            add_random_music_to_bumper(
                bumper_video_path=str(silent_video),
                output_path=str(output_path_obj),
                music_volume=cfg.get("music_volume", 0.2),
            )
            
            # Final validation after music is added
            if not validate_video_file(
                output_path_obj, min_duration_sec=duration_sec * 0.9
            ):
                print("[Weather] Final video with music failed validation", file=sys.stderr)
                return False
            
            return output_path_obj.exists()
        except Exception as e:
            print(f"[Weather] Failed to add music to bumper: {e}", file=sys.stderr)
            # Fallback: just copy the silent video
            shutil.copy(str(silent_video), str(output_path_obj))
            return output_path_obj.exists()


if __name__ == "__main__":
    import sys
    
    output = sys.argv[1] if len(sys.argv) > 1 else "weather_test.mp4"
    test_mode = "--test" in sys.argv or "-t" in sys.argv
    
    if test_mode:
        print("Running in test mode with mock weather data...")
    
    success = render_weather_bumper(output, test_mode=test_mode)
    if success:
        print(f"✓ Successfully rendered weather bumper to {output}")
    else:
        print("✗ Failed to render weather bumper", file=sys.stderr)
        if not test_mode:
            print("  Tip: Use --test flag to render with mock data without API", file=sys.stderr)
        sys.exit(1)

