"""Utility helpers for image tools – handles AVIF conversion via ffmpeg."""

import subprocess
import tempfile
from pathlib import Path
from PIL import Image


def open_image(filepath: Path) -> Image.Image:
    """Open an image file, using ffmpeg fallback for AVIF if Pillow can't handle it."""
    try:
        img = Image.open(filepath)
        img.load()  # Force load to catch errors early
        return img
    except Exception:
        # If it's an AVIF, try ffmpeg conversion to PNG in a temp file
        if filepath.suffix.lower() == ".avif":
            return _convert_avif_via_ffmpeg(filepath)
        raise


def _convert_avif_via_ffmpeg(filepath: Path) -> Image.Image:
    """Convert an AVIF file to PNG via ffmpeg and return as PIL Image."""
    tmp = Path(tempfile.mktemp(suffix=".png"))
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(filepath), str(tmp)],
            capture_output=True, text=True, timeout=60
        )
        if tmp.exists() and tmp.stat().st_size > 0:
            img = Image.open(tmp)
            img.load()  # Load into memory before deleting temp file
            return img
        else:
            raise RuntimeError(f"ffmpeg AVIF conversion failed: {result.stderr[-200:]}")
    finally:
        tmp.unlink(missing_ok=True)
