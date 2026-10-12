"""Lossless PDF compression preserving text, images, and document structure."""

import subprocess
import tempfile
from pathlib import Path
from tools.compression_utils import finish_compression, size_label


def run(input_dir: Path, output_dir: Path, options: dict, progress_cb=None):
    files = []

    def emit(event):
        if progress_cb:
            progress_cb(event)

    for path in sorted(input_dir.iterdir()):
        if not path.is_file() or path.name in (".gitkeep", "watermark.png"):
            continue
        if path.suffix.lower() == ".pdf":
            files.append(path)
        else:
            emit({"type": "log", "msg": f"⚠ Wrong file format for {path.name}, skipping."})

    total = len(files)
    completed = 0
    for index, source in enumerate(files, 1):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=output_dir, suffix=".pdf", delete=False) as handle:
                temporary = Path(handle.name)
            cmd = [
                "qpdf", "--compress-streams=y", "--decode-level=generalized",
                "--recompress-flate", "--compression-level=9", "--object-streams=generate",
                str(source), str(temporary),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                raise RuntimeError(result.stderr[-300:] or "QPDF reported a warning or error; original retained.")
            check = subprocess.run(["qpdf", "--check", str(temporary)], capture_output=True, text=True, timeout=60)
            if check.returncode != 0:
                raise RuntimeError(check.stderr[-300:] or "PDF output verification failed.")
            destination, before, after, saved, kept = finish_compression(source, temporary, output_dir, source.name)
            completed += 1
            detail = "already optimized; kept original bytes" if kept else f"saved {saved:.1f}%"
            emit({"type": "log", "msg": f"[{index}/{total}] ✓ {source.name} → {destination.name}: {size_label(before)} → {size_label(after)} ({detail})"})
        except Exception as error:
            emit({"type": "log", "msg": f"[{index}/{total}] ERROR: {source.name}: {error}"})
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            emit({"type": "progress", "value": int(index / total * 100)})

    emit({"type": "done", "msg": f"PDF compression complete. {completed} file(s) processed; {total - completed} left in /input."})
