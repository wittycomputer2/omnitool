"""Quality-controlled H.264 compression with verified, collision-safe outputs."""

import json
import subprocess
import tempfile
from pathlib import Path
from tools.compression_utils import finish_compression, size_label


def probe(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-300:] or "Unable to inspect video.")
    return json.loads(result.stdout)["streams"]


def run(input_dir: Path, output_dir: Path, options: dict, progress_cb=None):
    crf = int(options.get("crf", 20))
    preset = options.get("preset", "slow")
    if crf not in (18, 20, 23, 26):
        raise ValueError("Choose one of the supported video quality settings.")
    if preset not in ("fast", "medium", "slow"):
        raise ValueError("Choose fast, medium, or slow encoding.")
    strip_meta = options.get("strip_metadata", True)
    exts = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm"}
    files = []

    def emit(event):
        if progress_cb:
            progress_cb(event)

    for path in sorted(input_dir.iterdir()):
        if not path.is_file() or path.name in (".gitkeep", "watermark.png"):
            continue
        if path.suffix.lower() in exts:
            files.append(path)
        else:
            emit({"type": "log", "msg": f"⚠ Wrong file format for {path.name}, skipping."})

    total = len(files)
    completed = 0
    for index, source in enumerate(files, 1):
        temporary = None
        try:
            streams = probe(source)
            videos = [stream for stream in streams if stream.get("codec_type") == "video"]
            if not videos:
                raise ValueError("No video stream found.")
            if videos[0].get("color_transfer") in ("smpte2084", "arib-std-b67"):
                raise ValueError("HDR video is left intact to avoid changing its colors.")
            audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
            with tempfile.NamedTemporaryFile(dir=output_dir, suffix=".mp4", delete=False) as handle:
                temporary = Path(handle.name)
            cmd = [
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
                "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-crf", str(crf),
                "-preset", preset, "-pix_fmt", "yuv420p",
                "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-movflags", "+faststart",
            ]
            # Avoid another lossy encode when an audio track is already MP4-compatible.
            for track, stream in enumerate(audio):
                if stream.get("codec_name") == "aac":
                    cmd += [f"-c:a:{track}", "copy"]
                else:
                    cmd += [f"-c:a:{track}", "aac", f"-b:a:{track}", "192k"]
            if strip_meta:
                cmd += ["-map_metadata", "-1", "-map_chapters", "-1"]
            cmd.append(str(temporary))
            emit({"type": "log", "msg": f"[{index}/{total}] Compressing {source.name}…"})
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode != 0:
                raise RuntimeError(result.stderr[-300:] or "FFmpeg failed.")
            verified = probe(temporary)
            if not any(stream.get("codec_type") == "video" for stream in verified):
                raise RuntimeError("Output verification found no video stream.")
            if len([stream for stream in verified if stream.get("codec_type") == "audio"]) != len(audio):
                raise RuntimeError("Output verification found missing audio tracks.")
            # If encoding didn't shrink it, keep the original container and bytes.
            name = source.name if temporary.stat().st_size >= source.stat().st_size else f"{source.stem}.mp4"
            destination, before, after, saved, kept = finish_compression(source, temporary, output_dir, name)
            completed += 1
            detail = "already optimized; kept original bytes" if kept else f"saved {saved:.1f}%"
            emit({"type": "log", "msg": f"[{index}/{total}] ✓ {source.name} → {destination.name}: {size_label(before)} → {size_label(after)} ({detail})"})
        except Exception as error:
            emit({"type": "log", "msg": f"[{index}/{total}] ERROR: {source.name}: {error}"})
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            emit({"type": "progress", "value": int(index / total * 100)})

    emit({"type": "done", "msg": f"Video compression complete. {completed} file(s) processed; {total - completed} left in /input."})
