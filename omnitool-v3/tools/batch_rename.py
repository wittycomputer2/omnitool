"""Batch rename – Prefix_001.ext format with zero-padding."""

import random
import shutil
from pathlib import Path


def plan_names(files, options):
    """Assign batch names, optionally shuffling the numbering order."""
    prefix = str(options.get("prefix", "file")).strip()
    if any(char in prefix for char in ('/', '\\', '\0')):
        raise ValueError("Filename prefix cannot contain path separators or null characters.")
    start = int(options.get("start_number", 1))
    if start < 0:
        raise ValueError("Start number must be zero or greater.")
    ordered = list(files)
    if options.get("randomize_files", False):
        random.SystemRandom().shuffle(ordered)
    pad = max(3, len(str(start + len(ordered) - 1)))
    return {
        f: f"{prefix + '_' if prefix else ''}{str(start + i).zfill(pad)}{f.suffix.lower()}"
        for i, f in enumerate(ordered)
    }


def available_path(directory, name, reserved=None):
    """Keep existing files intact by adding a suffix to a conflicting name."""
    reserved = reserved if reserved is not None else set()
    path = directory / name
    candidate = path
    number = 1
    while candidate.exists() or candidate.name in reserved:
        candidate = path.with_name(f"{path.stem}_{number}{path.suffix}")
        number += 1
    reserved.add(candidate.name)
    return candidate


def run(input_dir: Path, output_dir: Path, options: dict, progress_cb=None):
    # Use a stable sorted order by default. When requested, shuffle first so
    # the sequence numbers are assigned to files in a random order.
    files = [f for f in sorted(input_dir.iterdir()) if f.is_file() and f.name.lower() != "watermark.png"]
    names = plan_names(files, options)
    files = list(names)
    total = len(files)

    if total == 0:
        if progress_cb:
            progress_cb({"type": "done", "msg": "No files found in /input."})
        return

    reserved = set()

    for i, f in enumerate(files):
        try:
            out_path = available_path(output_dir, names[f], reserved)
            new_name = out_path.name

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
