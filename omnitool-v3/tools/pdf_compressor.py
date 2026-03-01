"""PDF compressor using Ghostscript."""

import subprocess
from pathlib import Path


def run(input_dir: Path, output_dir: Path, options: dict, progress_cb=None):
    exts = {".pdf"}
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
                progress_cb({"type": "done", "msg": f"No PDF files found. {len(skipped)} file(s) with wrong format left intact in /input."})
            else:
                progress_cb({"type": "done", "msg": "No files found in /input."})
        return

    for i, f in enumerate(files, 1):
        try:
            out_path = output_dir / f.name

            cmd = [
                "gs",
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.4",
                "-dPDFSETTINGS=/ebook",
                "-dNOPAUSE", "-dQUIET", "-dBATCH",
                f"-sOutputFile={out_path}",
                str(f),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            if out_path.exists() and out_path.stat().st_size > 0:
                orig_size = f.stat().st_size
                new_size = out_path.stat().st_size
                saved = max(0, (1 - new_size / orig_size) * 100)
                f.unlink()
                if progress_cb:
                    progress_cb({"type": "log", "msg": f"[{i}/{total}] ✓ {f.name} (saved {saved:.1f}%)"})
            else:
                if progress_cb:
                    err = result.stderr[-200:] if result.stderr else "unknown error"
                    progress_cb({"type": "log", "msg": f"[{i}/{total}] ERROR: {f.name}: {err}"})

            if progress_cb:
                progress_cb({"type": "progress", "value": int(i / total * 100)})

        except Exception as e:
            if progress_cb:
                progress_cb({"type": "log", "msg": f"[{i}/{total}] ERROR: {f.name}: {e}"})
                progress_cb({"type": "progress", "value": int(i / total * 100)})

    done_msg = f"PDF compression complete. {total} files processed."
    if skipped:
        done_msg += f" {len(skipped)} file(s) with wrong format left intact."
    if progress_cb:
        progress_cb({"type": "done", "msg": done_msg})
