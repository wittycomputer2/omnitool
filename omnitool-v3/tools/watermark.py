"""Watermark tool – overlay watermark.png onto images with position & coverage control."""

import random
from pathlib import Path
from PIL import Image
from tools.image_utils import open_image


POSITIONS = {
    "top-left":     (0.02, 0.02),
    "top-right":    (0.98, 0.02),
    "center":       (0.50, 0.50),
    "bottom-left":  (0.02, 0.98),
    "bottom-right": (0.98, 0.98),
}


def _apply_watermark(bg: Image.Image, wm: Image.Image, position: str, coverage: float) -> Image.Image:
    """Apply watermark to a single image."""
    bg = bg.convert("RGBA")
    bg_w, bg_h = bg.size

    # Scale watermark so its width = coverage % of background width
    target_wm_w = max(1, int(bg_w * coverage / 100.0))
    wm_aspect = wm.height / wm.width
    target_wm_h = max(1, int(target_wm_w * wm_aspect))
    wm_resized = wm.resize((target_wm_w, target_wm_h), Image.LANCZOS)

    anchor_x, anchor_y = POSITIONS.get(position, (0.98, 0.98))

    paste_x = int(bg_w * anchor_x - target_wm_w * anchor_x)
    paste_y = int(bg_h * anchor_y - target_wm_h * anchor_y)

    paste_x = max(0, min(paste_x, bg_w - target_wm_w))
    paste_y = max(0, min(paste_y, bg_h - target_wm_h))

    layer = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    layer.paste(wm_resized, (paste_x, paste_y))

    result = Image.alpha_composite(bg, layer)
    return result.convert("RGB")


def preview(input_dir: Path, temp_dir: Path, options: dict) -> str | None:
    """Process one random image and save to /temp. Returns filename or None."""
    wm_path = input_dir / "watermark.png"
    if not wm_path.exists():
        return None

    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif", ".avif"}
    files = [f for f in input_dir.iterdir() if f.suffix.lower() in exts and f.name.lower() != "watermark.png"]
    if not files:
        return None

    f = random.choice(files)
    position = options.get("position", "bottom-right")
    coverage = float(options.get("coverage", 25))

    wm = Image.open(wm_path).convert("RGBA")
    bg = open_image(f)
    result = _apply_watermark(bg, wm, position, coverage)

    temp_dir.mkdir(exist_ok=True)
    # Clean old previews
    for old in temp_dir.iterdir():
        old.unlink()

    out_name = f"preview_{f.name}"
    if not out_name.lower().endswith((".jpg", ".jpeg", ".png")):
        out_name = f"preview_{f.stem}.jpg"
    out_path = temp_dir / out_name
    result.save(out_path, quality=95)
    return out_name


def run(input_dir: Path, output_dir: Path, options: dict, progress_cb=None):
    """Batch‑apply watermark to all images in /input."""
    wm_path = input_dir / "watermark.png"
    if not wm_path.exists():
        if progress_cb:
            progress_cb({"type": "log", "msg": "ERROR: watermark.png not found in /input."})
            progress_cb({"type": "done", "msg": "Aborted – no watermark.png."})
        return

    position = options.get("position", "bottom-right")
    coverage = float(options.get("coverage", 25))
    strip_meta = options.get("strip_metadata", True)

    wm = Image.open(wm_path).convert("RGBA")

    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif", ".avif"}
    all_files = [f for f in sorted(input_dir.iterdir()) if f.is_file() and f.name.lower() != "watermark.png"]
    files = [f for f in all_files if f.suffix.lower() in exts]
    skipped = [f for f in all_files if f.suffix.lower() not in exts]

    # Report wrong formats
    if progress_cb:
        for sf in skipped:
            progress_cb({"type": "log", "msg": f"⚠ Wrong file format for {sf.name}, skipping."})

    total = len(files)
    if total == 0:
        if progress_cb:
            if skipped:
                progress_cb({"type": "done", "msg": f"No compatible image files found. {len(skipped)} file(s) with wrong format left intact in /input."})
            else:
                progress_cb({"type": "done", "msg": "No image files found in /input."})
        return

    for i, f in enumerate(files, 1):
        try:
            bg = open_image(f)
            result = _apply_watermark(bg, wm, position, coverage)

            out_path = output_dir / f.name
            if not out_path.suffix.lower() in (".jpg", ".jpeg", ".png"):
                out_path = output_dir / f"{f.stem}.jpg"

            if strip_meta:
                clean = Image.new(result.mode, result.size)
                clean.putdata(list(result.getdata()))
                clean.save(out_path, quality=95)
            else:
                result.save(out_path, quality=95)

            if out_path.exists() and out_path.stat().st_size > 0:
                f.unlink()
                if progress_cb:
                    progress_cb({"type": "log", "msg": f"[{i}/{total}] Watermarked {f.name}"})
            else:
                if progress_cb:
                    progress_cb({"type": "log", "msg": f"[{i}/{total}] ERROR: verification failed for {f.name}"})

            if progress_cb:
                progress_cb({"type": "progress", "value": int(i / total * 100)})

        except Exception as e:
            if progress_cb:
                progress_cb({"type": "log", "msg": f"[{i}/{total}] ERROR: {f.name}: {e}"})
                progress_cb({"type": "progress", "value": int(i / total * 100)})

    done_msg = f"Watermarking complete. {total} files processed."
    if skipped:
        done_msg += f" {len(skipped)} file(s) with wrong format left intact."
    if progress_cb:
        progress_cb({"type": "done", "msg": done_msg})
