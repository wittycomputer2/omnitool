"""Just strip metadata – removes EXIF/metadata while preserving the original format (JPG, PNG, WEBP, AVIF)."""

from pathlib import Path
import subprocess
from PIL import Image
from tools.image_utils import open_image

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
            out_path = output_dir / f.name
            
            if f.suffix.lower() in (".mp3", ".mp4"):
                # Use ffmpeg to strip metadata without re-encoding
                cmd = ["ffmpeg", "-y", "-i", str(f), "-map_metadata", "-1", "-c", "copy", str(out_path)]
                subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            elif f.suffix.lower() == ".pdf":
                # Use Ghostscript to strip metadata
                cmd = [
                    "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
                    "-dNOPAUSE", "-dQUIET", "-dBATCH",
                    f"-sOutputFile={out_path}", str(f)
                ]
                subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            else:
                # Image processing (existing PIL logic)
                img = open_image(f)
                fmt = img.format
                if not fmt:
                    fmt = "JPEG" if f.suffix.lower() in (".jpg", ".jpeg") else f.suffix.upper()[1:]

                data = list(img.getdata())
                clean = Image.new(img.mode, img.size)
                clean.putdata(data)

                # Save options
                save_args = {}
                if fmt == "JPEG":
                    save_args["quality"] = 95
                    save_args["optimize"] = True
                elif fmt == "PNG":
                    save_args["optimize"] = True
                
                clean.save(out_path, format=fmt, **save_args)

            if out_path.exists() and out_path.stat().st_size > 0:
                f.unlink()
                if progress_cb:
                    progress_cb({"type": "log", "msg": f"[{i}/{total}] Stripped metadata from {f.name}"})
            else:
                if progress_cb:
                    progress_cb({"type": "log", "msg": f"[{i}/{total}] ERROR: verification failed for {f.name}"})

            if progress_cb:
                progress_cb({"type": "progress", "value": int(i / total * 100)})

        except Exception as e:
            if progress_cb:
                progress_cb({"type": "log", "msg": f"[{i}/{total}] ERROR: {f.name}: {e}"})
                progress_cb({"type": "progress", "value": int(i / total * 100)})

    done_msg = f"Metadata stripping complete. {total} files processed."
    if skipped:
        done_msg += f" {len(skipped)} file(s) with wrong format left intact."
    if progress_cb:
        progress_cb({"type": "done", "msg": done_msg})
