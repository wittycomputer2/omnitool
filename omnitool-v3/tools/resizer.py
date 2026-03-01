"""Advanced Image Resizer – Percentage or Fixed Dimension modes."""

from pathlib import Path
from PIL import Image
from tools.image_utils import open_image
import json, time


def run(input_dir: Path, output_dir: Path, options: dict, progress_cb=None):
    """
    options:
        mode        – "percentage" | "fixed"
        side        – "largest" | "smallest"    (only for fixed)
        target_size – int  (pixels for fixed, percent for percentage)
        strip_metadata – bool
    """
    mode = options.get("mode", "percentage")
    side = options.get("side", "largest")
    target = int(options.get("target_size", 50))
    strip_meta = options.get("strip_metadata", True)

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
                progress_cb({"type": "done", "msg": "No files found in /input."})
        return

    for i, f in enumerate(files, 1):
        try:
            img = open_image(f)
            w, h = img.size

            if mode == "percentage":
                factor = target / 100.0
                new_w = max(1, int(w * factor))
                new_h = max(1, int(h * factor))
            else:  # fixed
                if side == "largest":
                    if w >= h:
                        new_w = target
                        new_h = max(1, int(h / w * target))
                    else:
                        new_h = target
                        new_w = max(1, int(w / h * target))
                else:  # smallest
                    if w <= h:
                        new_w = target
                        new_h = max(1, int(h / w * target))
                    else:
                        new_h = target
                        new_w = max(1, int(w / h * target))

            img_resized = img.resize((new_w, new_h), Image.LANCZOS)

            out_path = output_dir / f.name
            if strip_meta:
                clean = Image.new(img_resized.mode, img_resized.size)
                clean.putdata(list(img_resized.getdata()))
                if clean.mode in ("RGBA", "P"):
                    clean = clean.convert("RGB")
                clean.save(out_path, quality=95)
            else:
                if img_resized.mode in ("RGBA", "P") and out_path.suffix.lower() in (".jpg", ".jpeg"):
                    img_resized = img_resized.convert("RGB")
                img_resized.save(out_path, quality=95)

            # Safety check
            if out_path.exists() and out_path.stat().st_size > 0:
                f.unlink()
                if progress_cb:
                    progress_cb({"type": "log", "msg": f"[{i}/{total}] Resized {f.name} → {new_w}x{new_h}"})
            else:
                if progress_cb:
                    progress_cb({"type": "log", "msg": f"[{i}/{total}] ERROR: output verification failed for {f.name}"})

            if progress_cb:
                progress_cb({"type": "progress", "value": int(i / total * 100)})

        except Exception as e:
            if progress_cb:
                progress_cb({"type": "log", "msg": f"[{i}/{total}] ERROR processing {f.name}: {e}"})
                progress_cb({"type": "progress", "value": int(i / total * 100)})

    done_msg = f"Resizing complete. {total} files processed."
    if skipped:
        done_msg += f" {len(skipped)} file(s) with wrong format left intact."
    if progress_cb:
        progress_cb({"type": "done", "msg": done_msg})
