"""Safe output handling shared by the compression tools."""

import shutil
from pathlib import Path
from tools.batch_rename import available_path


def finish_compression(source: Path, temporary: Path, output_dir: Path, name: str):
    """Publish a verified output, keeping the original bytes if they are smaller."""
    original_size = source.stat().st_size
    if not temporary.exists() or temporary.stat().st_size == 0:
        raise RuntimeError("Compression produced no usable output.")
    kept_original = temporary.stat().st_size >= original_size
    if kept_original:
        shutil.copy2(source, temporary)
    destination = available_path(output_dir, name)
    temporary.replace(destination)
    source.unlink()
    final_size = destination.stat().st_size
    saved = (1 - final_size / original_size) * 100 if original_size else 0
    return destination, original_size, final_size, saved, kept_original


def size_label(size):
    return f"{size / 1048576:.2f} MB" if size >= 1048576 else f"{size / 1024:.1f} KB"
