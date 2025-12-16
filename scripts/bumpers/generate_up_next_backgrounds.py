#!/usr/bin/env python3
"""
Pre-generate looping background videos for next-up bumpers.
These backgrounds are reusable - text is overlaid dynamically at playback time.
"""
from __future__ import annotations

import os
import sys
import tempfile
import math
import random
import secrets
import logging
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
from PIL import Image, ImageColor, ImageDraw

from scripts.bumpers.render_up_next import (
    create_vertical_gradient,
    create_pattern_layer,
    add_grain,
    choose_theme,
    THEME_PRESETS,
    LOGO_DEFAULT_PATH,
)
from scripts.bumpers.ffmpeg_utils import run_ffmpeg

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
LOGGER = logging.getLogger(__name__)

# Number of different background variations to generate
NUM_BACKGROUNDS = 5
LOOP_DURATION = 10.0  # 10 second loops (seamless)
FPS = 30


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


def _paste_logo(img: Image.Image, logo_path: Path, margin: int = 40) -> None:
    """Paste the HBN logo onto the image."""
    if not logo_path.exists():
        return
    try:
        logo_img = Image.open(logo_path).convert("RGBA")
        base_logo_width = 200
        scale = base_logo_width / logo_img.width
        resized = logo_img.resize(
            (int(logo_img.width * scale), int(logo_img.height * scale)),
            Image.LANCZOS,
        )
        img.paste(resized, (margin, margin), resized)
    except Exception:
        pass


def generate_background_video(
    background_id: int,
    output_path: Path,
    width: int = 1600,
    height: int = 900,
    fps: int = 30,
) -> bool:
    """Generate a looping background video for a specific next-up theme."""
    LOGGER.info("Generating background %d -> %s", background_id, output_path.name)
    
    # Resolve logo path
    assets_root = resolve_assets_root()
    logo_path = assets_root / "branding" / "hbn_logo_bug.png"
    
    # Use a deterministic seed based on background_id for consistency
    seed = background_id * 1000
    rng = random.Random(seed)
    noise_rng = np.random.default_rng(seed)
    
    # Choose theme (cycle through themes)
    theme_idx = background_id % len(THEME_PRESETS)
    theme = THEME_PRESETS[theme_idx].copy()
    
    # Add some variation but keep it deterministic
    from scripts.bumpers.render_up_next import _adjust_color
    theme["top"] = _adjust_color(theme["top"], rng.uniform(-0.05, 0.05))
    theme["bottom"] = _adjust_color(theme["bottom"], rng.uniform(-0.05, 0.05))
    theme["accent"] = _adjust_color(theme["accent"], rng.uniform(-0.04, 0.04))
    theme["pattern"] = _adjust_color(theme["pattern"], rng.uniform(-0.03, 0.03))
    
    # Animation parameters (deterministic)
    brightness_amp = 0.012 + (background_id % 3) * 0.004
    brightness_freq = 0.25 + (background_id % 5) * 0.02
    brightness_phase = (background_id % 10) * 0.2
    pattern_freq = 0.18 + (background_id % 4) * 0.04
    pattern_phase = (background_id % 8) * 0.25
    pattern_amp = 0.25 + (background_id % 3) * 0.07
    grain_opacity = 0.22 + (background_id % 5) * 0.02
    
    # Generate pattern layer base
    pattern_layer_base = create_pattern_layer(
        width,
        height,
        theme["pattern"],
        opacity=0.12 + (background_id % 3) * 0.02,
        rng=rng,
    )
    
    # Generate frames for seamless loop
    total_frames = int(LOOP_DURATION * fps)
    
    with tempfile.TemporaryDirectory(prefix=f"upnext_bg_{background_id}_") as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        
        LOGGER.info("Rendering %d frames for seamless %ds loop...", total_frames, LOOP_DURATION)
        
        for frame_num in range(total_frames):
            t = frame_num / fps
            
            # Create base gradient
            frame = create_vertical_gradient(
                width, height, theme["top"], theme["bottom"]
            )
            
            # Add brightness animation
            brightness_jitter = 1 + brightness_amp * math.sin(
                2 * math.pi * brightness_freq * t + brightness_phase
            )
            frame_np = np.clip(
                np.array(frame, dtype=np.float32) * brightness_jitter,
                0,
                255,
            ).astype(np.uint8)
            frame = Image.fromarray(frame_np).convert("RGBA")
            
            # Add animated pattern layer
            pattern_factor = max(
                0.1,
                min(
                    1.0,
                    0.6
                    + pattern_amp
                    * math.sin(2 * math.pi * pattern_freq * t + pattern_phase),
                ),
            )
            pattern_layer = pattern_layer_base.copy()
            alpha_channel = pattern_layer.split()[3].point(
                lambda a: int(max(0, min(255, a * pattern_factor)))
            )
            pattern_layer.putalpha(alpha_channel)
            frame = Image.alpha_composite(frame, pattern_layer)
            
            # Add grain
            frame = add_grain(frame, opacity=grain_opacity, noise_rng=noise_rng)
            
            # Add logo (static, same on all frames)
            if logo_path.exists():
                _paste_logo(frame, logo_path)
            
            # Convert to RGB for video encoding
            frame_rgb = Image.new("RGB", frame.size, (0, 0, 0))
            frame_rgb.paste(frame, (0, 0), frame)
            
            # Save frame
            frame_path = tmp_dir_path / f"frame_{frame_num:04d}.png"
            frame_rgb.save(frame_path)
            
            # Progress logging
            if (frame_num + 1) % 30 == 0 or frame_num == total_frames - 1:
                progress = int(100 * (frame_num + 1) / total_frames)
                LOGGER.debug("Frame progress: %d%% (%d/%d)", progress, frame_num + 1, total_frames)
            if (frame_num + 1) % 100 == 0:
                LOGGER.info("Rendered %d/%d frames (%.1f%%)", frame_num + 1, total_frames, 100 * (frame_num + 1) / total_frames)
        
        # Encode looping video
        LOGGER.info("Encoding video with FFmpeg (preset=fast, crf=20, threads=0)...")
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
            "fast",  # Changed from "medium" to "fast" for faster encoding on beefy systems
            "-threads", "0",  # Use all available CPU threads
            "-crf",
            "20",  # Slightly higher CRF (lower quality but faster) - still good quality
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
            run_ffmpeg(video_cmd, timeout=300.0, description=f"Encoding background {background_id}")  # Increased timeout to 5 minutes
            file_size_mb = output_path.stat().st_size / (1024 * 1024)
            LOGGER.info("✓ Successfully generated background %d: %s (%.1f MB)", background_id, output_path.name, file_size_mb)
            return True
        except Exception as e:
            LOGGER.error("✗ Failed to encode background %d: %s", background_id, e, exc_info=True)
            return False


def generate_all_backgrounds(force: bool = False) -> None:
    """Generate all next-up background variations."""
    assets_root = resolve_assets_root()
    backgrounds_dir = assets_root / "bumpers" / "up_next" / "backgrounds"
    
    LOGGER.info("=" * 60)
    LOGGER.info("Generating reusable next-up bumper backgrounds")
    LOGGER.info("Output directory: %s", backgrounds_dir)
    LOGGER.info("Number of backgrounds: %d", NUM_BACKGROUNDS)
    LOGGER.info("Loop duration: %.1fs, FPS: %d", LOOP_DURATION, FPS)
    LOGGER.info("Force regenerate: %s", force)
    LOGGER.info("=" * 60)
    
    backgrounds_dir.mkdir(parents=True, exist_ok=True)
    
    generated = 0
    skipped = 0
    failed = 0
    
    for bg_id in range(NUM_BACKGROUNDS):
        output_path = backgrounds_dir / f"bg_{bg_id:02d}.mp4"
        
        if output_path.exists() and not force:
            file_size_mb = output_path.stat().st_size / (1024 * 1024)
            # Validate file size - corrupted files (< 1MB) should be regenerated
            if file_size_mb < 1.0:
                LOGGER.warning("Background %d exists but is corrupted (%s, %.1f MB), regenerating...", bg_id, output_path.name, file_size_mb)
                # Delete corrupted file
                output_path.unlink()
                force_regenerate = True
            else:
                LOGGER.info("Background %d already exists (%s, %.1f MB), skipping...", bg_id, output_path.name, file_size_mb)
                skipped += 1
                continue
        else:
            force_regenerate = False
        
        LOGGER.info("-" * 60)
        if generate_background_video(bg_id, output_path):
            generated += 1
        else:
            failed += 1
    
    LOGGER.info("=" * 60)
    LOGGER.info("Generation complete! Generated: %d, Skipped: %d, Failed: %d", generated, skipped, failed)
    if generated > 0:
        LOGGER.info("Backgrounds are ready for fast bumper rendering!")


if __name__ == "__main__":
    force = "--force" in sys.argv or "-f" in sys.argv
    generate_all_backgrounds(force=force)

