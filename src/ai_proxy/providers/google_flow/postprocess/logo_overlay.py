"""Cover Flow's visible watermark with a branding logo, via ffmpeg.

Reverse-alpha-blend watermark *removal* (see
`docs/google-flow-wrapper-module/watermark-removal-plan.md`) was tried against a real Flow
output image and produced visible artifacts, because Flow's watermark doesn't match the alpha
maps that tool was calibrated against. This module instead stamps an opaque logo on top of the
watermark's position, measured from a real 1376x768 Flow output: ~48px from the right edge and
~56px from the bottom edge, scaled down to roughly the watermark's own footprint (75x74px).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

# Measured against a real 1376x768 Flow output image (see watermark-removal-plan.md).
LOGO_WIDTH = 75
LOGO_HEIGHT = 74
MARGIN_RIGHT = 48
MARGIN_BOTTOM = 56

# Flow's downloads are JPEG bytes saved with a .png name (see flowpage/download.py); re-encoding
# losslessly as PNG here would balloon a ~250KB photo into several MB for no visual benefit.
JPEG_QUALITY = 2


class LogoOverlayError(RuntimeError):
    """Raised when ffmpeg is unavailable or fails to overlay the logo."""


def ffmpeg_available() -> bool:
    """Whether the `ffmpeg` binary can be found on PATH."""
    return shutil.which("ffmpeg") is not None


def overlay_logo(image_path: Path, logo_path: Path, output_path: Path) -> None:
    """Scale `logo_path` down and stamp it over the watermark position in `image_path`."""
    if not ffmpeg_available():
        raise LogoOverlayError("ffmpeg not found on PATH")
    # W/H = main image dimensions, w/h = the scaled overlay's dimensions (ffmpeg overlay aliases).
    filter_complex = (
        f"[1:v]scale={LOGO_WIDTH}:{LOGO_HEIGHT}[wm];"
        f"[0:v][wm]overlay=W-w-{MARGIN_RIGHT}:H-h-{MARGIN_BOTTOM}"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(image_path),
        "-i",
        str(logo_path),
        "-filter_complex",
        filter_complex,
        "-frames:v",
        "1",
        "-update",
        "1",
        # Force JPEG output explicitly: the output path may have a non-standard extension (e.g. a
        # ".png.tmp" staging file) that ffmpeg can't infer a muxer/codec from, and encoding as PNG
        # would re-compress a lossy source losslessly, ballooning file size (see JPEG_QUALITY).
        "-f",
        "image2",
        "-c:v",
        "mjpeg",
        "-q:v",
        str(JPEG_QUALITY),
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise LogoOverlayError(f"ffmpeg overlay failed: {result.stderr.strip()}")


def overlay_logo_in_place(image_path: Path, logo_path: Path) -> None:
    """Overlay the logo and replace `image_path`'s contents with the result."""
    tmp_path = image_path.with_suffix(image_path.suffix + ".tmp")
    overlay_logo(image_path, logo_path, tmp_path)
    tmp_path.replace(image_path)
