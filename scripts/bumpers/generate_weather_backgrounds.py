#!/usr/bin/env python3
"""
Pre-generate looping background videos for weather effects.
These backgrounds are reusable - text is overlaid dynamically at playback time.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.bumpers.render_weather_bumper import (
    _draw_clouds,
    _draw_fog,
    _draw_raindrops,
    _draw_snowflakes,
    _draw_sun_rays,
    _make_gradient_bg,
    _paste_logo,
    resolve_assets_root,
)
from scripts.bumpers.ffmpeg_utils import run_ffmpeg
from PIL import Image

WEATHER_EFFECTS = ["snow", "rain", "fog", "sun", "clouds"]
LOOP_DURATION = 10.0  # 10 second loops (seamless)


def generate_background_video(
    effect_type: str,
    output_path: Path,
    width: int = 1600,
    height: int = 900,
    fps: int = 30,
    intensity: float = 1.0,
) -> bool:
    """Generate a looping background video for a specific weather effect."""
    print(f"[Weather Background] Generating {effect_type} background...")
    
    # Resolve logo path
    assets_root = resolve_assets_root()
    logo_path = assets_root / "branding" / "hbn_logo_bug.png"
    
    # Generate frames for seamless loop
    total_frames = int(LOOP_DURATION * fps)
    
    with tempfile.TemporaryDirectory(prefix=f"weather_bg_{effect_type}_") as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        
        print(f"  Rendering {total_frames} frames...")
        
        for frame_num in range(total_frames):
            # Create base gradient background
            img = _make_gradient_bg(width, height)
            
            # Convert to RGBA for transparency support
            img = img.convert("RGBA")
            
            # Draw weather effects
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
            
            # Convert back to RGB
            base_img = Image.new("RGB", (width, height), (0, 0, 0))
            base_img.paste(img, (0, 0), img)
            img = base_img
            
            # Add logo (static, same on all frames)
            if logo_path.exists():
                _paste_logo(img, logo_path)
            
            # Save frame
            frame_path = tmp_dir_path / f"frame_{frame_num:04d}.png"
            img.save(frame_path)
            
            # Progress
            if (frame_num + 1) % 30 == 0 or frame_num == total_frames - 1:
                progress = int(100 * (frame_num + 1) / total_frames)
                print(f"  Progress: {progress}% ({frame_num + 1}/{total_frames})")
        
        # Encode looping video
        print(f"  Encoding video...")
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
            "-t",
            str(LOOP_DURATION),
            "-r",
            str(fps),
            "-an",  # No audio in background
            str(output_path),
        ]
        
        try:
            run_ffmpeg(video_cmd, timeout=180.0, description=f"Encoding {effect_type} background")
            print(f"  ✓ Generated: {output_path}")
            return True
        except Exception as e:
            print(f"  ✗ Failed to encode: {e}", file=sys.stderr)
            return False


def generate_all_backgrounds(force: bool = False) -> None:
    """Generate all weather effect backgrounds."""
    assets_root = resolve_assets_root()
    backgrounds_dir = assets_root / "bumpers" / "weather"
    backgrounds_dir.mkdir(parents=True, exist_ok=True)
    
    print("[Weather Background] Generating reusable weather effect backgrounds...")
    print(f"Output directory: {backgrounds_dir}\n")
    
    generated = 0
    skipped = 0
    
    for effect_type in WEATHER_EFFECTS:
        output_path = backgrounds_dir / f"bg_{effect_type}.mp4"
        
        if output_path.exists() and not force:
            print(f"[Weather Background] {effect_type} background already exists, skipping...")
            skipped += 1
            continue
        
        intensity = 1.5 if effect_type in ["snow", "rain"] else 1.0
        
        if generate_background_video(effect_type, output_path, intensity=intensity):
            generated += 1
        print()
    
    print(f"[Weather Background] Done! Generated: {generated}, Skipped: {skipped}")


if __name__ == "__main__":
    force = "--force" in sys.argv or "-f" in sys.argv
    generate_all_backgrounds(force=force)

