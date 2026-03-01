"""Metadata stripper & JPG converter – strips EXIF and converts PNG/WEBP/HEIC/AVIF to high-quality JPG."""

from pathlib import Path
from PIL import Image
from tools.image_utils import open_image

# Try to register HEIF support
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

import subprocess


def run(input_dir: Path, output_dir: Path, options: dict, progress_cb=None):
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif", ".heic", ".heif", ".avif", ".mp3", ".pdf", ".mp4"}
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
            if f.suffix.lower() in (".mp3", ".mp4"):
                # Use ffmpeg to strip metadata (preserving format)
                out_path = output_dir / f.name
                cmd = ["ffmpeg", "-y", "-i", str(f), "-map_metadata", "-1", "-c", "copy", str(out_path)]
                subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                msg = f"stripped metadata from {f.name}"
            elif f.suffix.lower() == ".pdf":
                # Use Ghostscript to strip metadata (preserving format)
                out_path = output_dir / f.name
                cmd = [
                    "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
                    "-dNOPAUSE", "-dQUIET", "-dBATCH",
                    f"-sOutputFile={out_path}", str(f)
                ]
                subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                msg = f"stripped metadata from {f.name}"
            else:
                # Image processing (convert to JPG and strip)
                img = open_image(f)

                # Convert to RGB (strip alpha)
                if img.mode in ("RGBA", "P", "LA"):
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                    img = bg
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                # Create a clean image with NO metadata
                clean = Image.new("RGB", img.size)
                clean.putdata(list(img.getdata()))

                out_path = output_dir / f"{f.stem}.jpg"
                clean.save(out_path, "JPEG", quality=95)
                msg = f"{f.name} → {out_path.name} (metadata stripped)"

            if out_path.exists() and out_path.stat().st_size > 0:
                f.unlink()
                if progress_cb:
                    progress_cb({"type": "log", "msg": f"[{i}/{total}] {msg}"})
            else:
                if progress_cb:
                    progress_cb({"type": "log", "msg": f"[{i}/{total}] ERROR: verification failed for {f.name}"})

            if progress_cb:
                progress_cb({"type": "progress", "value": int(i / total * 100)})

        except Exception as e:
            if progress_cb:
                progress_cb({"type": "log", "msg": f"[{i}/{total}] ERROR: {f.name}: {e}"})
                progress_cb({"type": "progress", "value": int(i / total * 100)})

    done_msg = f"Conversion complete. {total} files processed."
    if skipped:
        done_msg += f" {len(skipped)} file(s) with wrong format left intact."
    if progress_cb:
        progress_cb({"type": "done", "msg": done_msg})
