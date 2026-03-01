"""WAV to MP3 converter using ffmpeg."""

import subprocess
from pathlib import Path


def run(input_dir: Path, output_dir: Path, options: dict, progress_cb=None):
    bitrate = options.get("bitrate", "192k")
    strip_meta = options.get("strip_metadata", True)

    exts = {".wav"}
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
                progress_cb({"type": "done", "msg": f"No .wav files found. {len(skipped)} file(s) with wrong format left intact in /input."})
            else:
                progress_cb({"type": "done", "msg": "No files found in /input."})
        return

    for i, f in enumerate(files, 1):
        try:
            out_path = output_dir / f"{f.stem}.mp3"

            cmd = [
                "ffmpeg", "-y", "-i", str(f),
                "-vn", "-ar", "44100", "-ac", "2",
                "-b:a", bitrate,
            ]
            if strip_meta:
                cmd += ["-map_metadata", "-1"]
            cmd.append(str(out_path))

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if out_path.exists() and out_path.stat().st_size > 0:
                f.unlink()
                if progress_cb:
                    progress_cb({"type": "log", "msg": f"[{i}/{total}] Converted {f.name} → {out_path.name} ({bitrate})"})
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

    done_msg = f"Audio conversion complete. {total} files processed."
    if skipped:
        done_msg += f" {len(skipped)} file(s) with wrong format left intact."
    if progress_cb:
        progress_cb({"type": "done", "msg": done_msg})
