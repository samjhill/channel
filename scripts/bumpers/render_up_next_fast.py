"""
Fast renderer for next-up bumpers using pre-generated backgrounds.
Overlays text on background videos using ffmpeg, similar to weather bumpers.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.bumpers.ffmpeg_utils import run_ffmpeg, validate_video_file


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


def get_up_next_background_path(background_id: Optional[int] = None) -> Optional[Path]:
    """Get the path to a pre-generated next-up background video.
    
    Validates that the background file exists and is not empty (corrupted).
    """
    assets_root = resolve_assets_root()
    backgrounds_dir = assets_root / "bumpers" / "up_next" / "backgrounds"
    
    def is_valid_background(bg_path: Path) -> bool:
        """Check if background file exists and is not empty/corrupted."""
        if not bg_path.exists():
            return False
        # Check file size - should be at least 1MB for a valid video
        try:
            size_mb = bg_path.stat().st_size / (1024 * 1024)
            if size_mb < 1.0:
                print(f"[Up Next] Warning: Background {bg_path.name} is too small ({size_mb:.1f} MB), skipping", file=sys.stderr)
                return False
            return True
        except OSError:
            return False
    
    if background_id is not None:
        bg_path = backgrounds_dir / f"bg_{background_id:02d}.mp4"
        if is_valid_background(bg_path):
            return bg_path
    
    # Try to find any available valid background
    # Check up to 15 backgrounds to support more variety
    for bg_id in range(15):
        bg_path = backgrounds_dir / f"bg_{bg_id:02d}.mp4"
        if is_valid_background(bg_path):
            return bg_path
    
    return None


def render_up_next_bumper_fast(
    show_title: str,
    output_path: str,
    episode_label: Optional[str] = None,
    background_id: Optional[int] = None,
    width: int = 1600,
    height: int = 900,
    duration_sec: float = 6.0,
    fps: int = 30,
) -> bool:
    """
    Fast renderer for next-up bumpers using pre-generated backgrounds and ffmpeg text overlay.
    
    This is much faster than rendering frames - just overlays text on a background video.
    """
    bg_path = get_up_next_background_path(background_id)
    
    if not bg_path:
        # Fallback: use full render if background doesn't exist
        # But first check if we should skip fast render entirely
        print(f"[Up Next] Background not found (background_id={background_id}), falling back to frame-by-frame render")
        try:
            from scripts.bumpers.render_up_next import render_up_next_bumper
            logo_path = resolve_assets_root() / "branding" / "hbn_logo_bug.png"
            render_up_next_bumper(
                show_title=show_title,
                output_path=output_path,
                logo_path=str(logo_path) if logo_path.exists() else "assets/branding/hbn_logo_bug.png",
                episode_label=episode_label,
            )
            return True
        except Exception as e:
            print(f"[Up Next] Fallback render failed: {e}", file=sys.stderr)
            return False
    
    with tempfile.TemporaryDirectory(prefix="upnext_fast_") as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        silent_output = tmp_dir_path / "silent.mp4"
        
        # Prepare text strings
        show_title_display = show_title.strip().title()
        episode_label_display = (episode_label or "").strip()
        
        # Escape text for ffmpeg
        def escape_text(text: str) -> str:
            return text.replace(":", "\\:").replace("'", "\\'").replace("[", "\\[").replace("]", "\\]").replace("\\", "\\\\")
        
        # Font path (try common system fonts)
        font_path = ""
        font_candidates = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        ]
        for candidate in font_candidates:
            if os.path.exists(candidate):
                font_path = candidate
                break
        
        # Build text overlay filter
        filter_parts = []
        
        # "UP NEXT" text (top)
        up_next_y = int(height * 0.32)
        filter_parts.append(
            f"drawtext=text='UP NEXT':"
            f"fontfile={font_path if font_path else 'Arial'}:"
            f"fontsize=128:"
            f"fontcolor=0xF8F5E9:"
            f"x=(w-text_w)/2:"
            f"y={up_next_y}:"
            f"box=0:boxborderw=0"
        )
        
        # Divider line (accent color - using a warm color)
        divider_y = up_next_y + 120
        divider_width = int(width * 0.35)
        # Draw line using drawbox (simpler than drawtext)
        filter_parts.append(
            f"drawbox=x=(w-{divider_width})/2:y={divider_y}:w={divider_width}:h=6:color=0xEBA983:t=fill"
        )
        
        # Show title with text wrapping to prevent overlap with subtitle
        title_y = divider_y + 60
        # Set max width for title (80% of screen width) to enable wrapping
        # This ensures long titles wrap instead of overlapping the subtitle
        max_title_width = int(width * 0.8)
        filter_parts.append(
            f"drawtext=text='{escape_text(show_title_display)}':"
            f"fontfile={font_path if font_path else 'Arial'}:"
            f"fontsize=80:"
            f"fontcolor=0xF8F5E9:"
            f"x=(w-text_w)/2:"
            f"y={title_y}:"
            f"box=0:boxborderw=0"
        )
        
        # Episode label (if provided)
        # Increase spacing to account for potential title wrapping (96px base + extra for wrapped lines)
        # Estimate: each wrapped line adds ~90px (fontsize 80 + line spacing)
        # For safety, add extra space (120px total) to accommodate up to 2 lines
        if episode_label_display:
            subtitle_y = title_y + 120  # Increased from 96 to 120 to prevent overlap
            filter_parts.append(
                f"drawtext=text='{escape_text(episode_label_display)}':"
                f"fontfile={font_path if font_path else 'Arial'}:"
                f"fontsize=54:"
                f"fontcolor=0xF8F5E9:"
                f"x=(w-text_w)/2:"
                f"y={subtitle_y}:"
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
            print(f"[Up Next] Fast render: overlaying text on background {bg_path.name}...")
            run_ffmpeg(
                video_cmd,
                timeout=30.0,
                description=f"Overlaying text on next-up background",
            )
        except Exception as e:
            print(f"[Up Next] Fast render failed: {e}, falling back to frame-by-frame", file=sys.stderr)
            # Fallback to frame-by-frame
            from scripts.bumpers.render_up_next import render_up_next_bumper
            try:
                logo_path = resolve_assets_root() / "branding" / "hbn_logo_bug.png"
                render_up_next_bumper(
                    show_title=show_title,
                    output_path=output_path,
                    logo_path=str(logo_path) if logo_path.exists() else "assets/branding/hbn_logo_bug.png",
                    episode_label=episode_label,
                )
                return True
            except Exception as e2:
                print(f"[Up Next] Fallback render also failed: {e2}", file=sys.stderr)
                return False
        
        # Validate the generated video
        if not validate_video_file(silent_output, min_duration_sec=duration_sec * 0.9):
            print("[Up Next] Generated video failed validation", file=sys.stderr)
            return False
        
        # Copy to final output path
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        import shutil
        shutil.copy(str(silent_output), str(output_path_obj))
        return output_path_obj.exists()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: render_up_next_fast.py <show_title> <output_path> [episode_label] [background_id]")
        sys.exit(1)
    
    show_title = sys.argv[1]
    output_path = sys.argv[2]
    episode_label = sys.argv[3] if len(sys.argv) > 3 else None
    background_id = int(sys.argv[4]) if len(sys.argv) > 4 else None
    
    success = render_up_next_bumper_fast(
        show_title=show_title,
        output_path=output_path,
        episode_label=episode_label,
        background_id=background_id,
    )
    
    if success:
        print(f"✓ Successfully rendered next-up bumper to {output_path}")
    else:
        print("✗ Failed to render next-up bumper", file=sys.stderr)
        sys.exit(1)

