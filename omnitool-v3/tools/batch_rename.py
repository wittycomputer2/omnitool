"""Batch rename – Prefix_001.ext format with zero-padding."""

import shutil
from pathlib import Path


def run(input_dir: Path, output_dir: Path, options: dict, progress_cb=None):
    prefix = options.get("prefix", "file")
    start_number = int(options.get("start_number", 1))

    # Exclude watermark.png
    files = [f for f in sorted(input_dir.iterdir()) if f.is_file() and f.name.lower() != "watermark.png"]
    total = len(files)

    if total == 0:
        if progress_cb:
            progress_cb({"type": "done", "msg": "No files found in /input."})
        return

    # Determine zero-padding width
    max_num = start_number + total - 1
    pad = max(3, len(str(max_num)))

    for i, f in enumerate(files):
        try:
            num = start_number + i
            new_name = f"{prefix}_{str(num).zfill(pad)}{f.suffix.lower()}"
            out_path = output_dir / new_name

            shutil.copy2(str(f), str(out_path))

            if out_path.exists() and out_path.stat().st_size > 0:
                f.unlink()
                if progress_cb:
                    progress_cb({"type": "log", "msg": f"[{i+1}/{total}] {f.name} → {new_name}"})
            else:
                if progress_cb:
                    progress_cb({"type": "log", "msg": f"[{i+1}/{total}] ERROR: verification failed for {f.name}"})

            if progress_cb:
                progress_cb({"type": "progress", "value": int((i + 1) / total * 100)})

        except Exception as e:
            if progress_cb:
                progress_cb({"type": "log", "msg": f"[{i+1}/{total}] ERROR: {f.name}: {e}"})
                progress_cb({"type": "progress", "value": int((i + 1) / total * 100)})

    if progress_cb:
        progress_cb({"type": "done", "msg": f"Batch rename complete. {total} files renamed."})
