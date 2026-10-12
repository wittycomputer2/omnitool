OmniTool v3.2.0 adds image compression and improves repeated file-processing workflows.

- Image Compression for JPG, PNG, and WebP, with adjustable quality, optional lossless WebP, and before/after sizes.
- Advanced Resizer defaults to Fixed Dimension.
- Optional renaming during resizing and JPG conversion, including prefix, numbering, and randomized numbering.
- Move output files back to input from the toolbar, preserving files when names conflict.
- Video Compression offers quality and speed controls, preserves AAC audio, and verifies output before removing input.
- PDF compression remains lossless and verifies output before removing input.
- Compression keeps original bytes when a result would be larger.
- Python, FFmpeg/FFprobe, QPDF, Ghostscript, and shared libraries are bundled.
- Startup automatically chooses another local port if an older instance occupies port 5000.

For upgrades, replace the old AppImage and update any desktop shortcut. Keep existing input/output folders. Check for v3.2.0 in the sidebar.

On Debian GNOME, if double-clicking fails or opens an older version, launch the new file directly:

```bash
chmod +x OmniTool-x86_64.AppImage
./OmniTool-x86_64.AppImage --appimage-extract-and-run
```

The executable is for Linux x86_64. SHA-256 verification is included with the release.

Validation: 31 automated tests and the bundled offline self-test passed.
