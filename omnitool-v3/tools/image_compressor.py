"""Compress JPG, PNG, and WebP images without resizing or changing format."""

import tempfile
from pathlib import Path
from PIL import Image, ImageOps, JpegImagePlugin, PngImagePlugin
from tools.compression_utils import finish_compression, size_label


def run(input_dir: Path, output_dir: Path, options: dict, progress_cb=None):
    quality = int(options.get("quality", 85))
    if not 1 <= quality <= 100:
        raise ValueError("Image quality must be between 1 and 100.")
    strip_metadata = options.get("strip_metadata", True)
    lossless_webp = options.get("lossless_webp", False)
    files = []

    def emit(event):
        if progress_cb:
            progress_cb(event)

    for path in sorted(input_dir.iterdir()):
        if not path.is_file() or path.name in (".gitkeep", "watermark.png"):
            continue
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            files.append(path)
        else:
            emit({"type": "log", "msg": f"⚠ Unsupported image format: {path.name}, left in /input."})

    total = len(files)
    completed = 0
    for index, source in enumerate(files, 1):
        temporary = None
        try:
            with Image.open(source) as original:
                if getattr(original, "is_animated", False):
                    emit({"type": "log", "msg": f"⚠ {source.name} is animated, left intact in /input."})
                    continue
                original.load()
                sampling = JpegImagePlugin.get_sampling(original) if original.format == "JPEG" else -1
                image = ImageOps.exif_transpose(original)
                save_options = {}
                # Keep color profiles even when stripping descriptive metadata.
                if original.info.get("icc_profile"):
                    save_options["icc_profile"] = original.info["icc_profile"]
                if not strip_metadata:
                    if image.getexif():
                        save_options["exif"] = image.getexif().tobytes()
                    if original.info.get("dpi"):
                        save_options["dpi"] = original.info["dpi"]
                    if image.info.get("xmp"):
                        save_options["xmp"] = image.info["xmp"]
                    if original.format == "PNG":
                        png_info = PngImagePlugin.PngInfo()
                        for key, value in original.text.items():
                            png_info.add_itxt(key, value)
                        save_options["pnginfo"] = png_info

                if original.format == "JPEG":
                    save_options.update(quality=quality, optimize=True, progressive=True,
                                        subsampling=sampling if sampling in (0, 1, 2) else 0)
                elif original.format == "PNG":
                    save_options.update(optimize=True, compress_level=9)
                elif original.format == "WEBP":
                    save_options.update(quality=quality, method=6, lossless=lossless_webp,
                                        exact=True)
                else:
                    raise ValueError("File contents are not JPG, PNG, or WebP.")
                # Clear metadata on the new image so Pillow cannot copy it implicitly.
                image.info.clear()
                with tempfile.NamedTemporaryFile(dir=output_dir, suffix=source.suffix, delete=False) as handle:
                    temporary = Path(handle.name)
                image.save(temporary, format=original.format, **save_options)
                with Image.open(temporary) as verified:
                    verified.load()
                    if verified.size != image.size:
                        raise RuntimeError("Output dimensions failed verification.")

            destination, before, after, saved, kept_original = finish_compression(source, temporary, output_dir, source.name)
            completed += 1
            detail = "already optimized; kept original bytes" if kept_original else f"saved {saved:.1f}%"
            emit({"type": "log", "msg": f"[{index}/{total}] ✓ {source.name} → {destination.name}: {size_label(before)} → {size_label(after)} ({detail})"})
        except Exception as error:
            emit({"type": "log", "msg": f"[{index}/{total}] ERROR: {source.name}: {error}"})
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            emit({"type": "progress", "value": int(index / total * 100)})

    emit({"type": "done", "msg": f"Image compression complete. {completed} file(s) processed; {total - completed} left in /input."})
