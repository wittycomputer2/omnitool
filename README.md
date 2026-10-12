

🚀 How to Run OmniTool
Option 1: Using the AppImage (Easiest)
The OmniTool AppImage is a pre-compiled bundle for Linux. No installation is required.

> **Quick Start:** [🚀 Download the Latest AppImage for Linux](https://github.com/wittycomputer2/omnitool/releases/download/v3.2.0/OmniTool-x86_64.AppImage)

Locate the .AppImage file you downloaded.

Right-click the file and select Properties.

Go to the Permissions tab and check "Allow executing file as program".

Double-click the file to launch the workshop.

Option 2: Run from Source (For Developers)
If you prefer to run the code manually or contribute to the project:

Clone the repository:

Bash
git clone https://github.com/wittycomputer2/omnitool.git
Install requirements:

Bash
pip install -r requirements.txt
Launch:

Bash
python app.py

🎓 Learning Resources: Need help setting up your digital environment? Visit https://university.witty.computer for full documentation and video guides provided by the Witty Computer Digital Workshop.  Special thanks to https://neonghost.net for their support.

### Image Compression update

Image Compression appears immediately above Video Compression. It keeps JPG,
PNG, and WebP formats, provides adjustable JPG/WebP quality, and offers lossless
WebP compression. PNG compression is lossless. Animated images remain in input.
The console reports original and resulting sizes; if compression would make a
file larger, the original bytes are moved to output instead.

Video Compression now offers quality and speed settings, preserves AAC audio,
and checks output before removing the input. PDF compression uses lossless QPDF
optimization, preserving selectable text and image quality. All compression
tools preserve existing output files when filenames conflict.

The rebuilt `OmniTool-x86_64.AppImage` bundles Python, FFmpeg/FFprobe, QPDF,
Ghostscript, and their shared libraries. Users do not need to install those
packages. Input, output, temporary files, and watermarks live beside the AppImage,
so put it in a folder you can write to.

If FUSE mounting is unavailable, run it without FUSE:

```bash
./OmniTool-x86_64.AppImage --appimage-extract-and-run
```

Run its bundled offline verification:

```bash
./OmniTool-x86_64.AppImage --appimage-extract-and-run --self-test
```

To rebuild on Linux x86_64, install the **build dependencies** (`squashfs-tools`,
`ffmpeg`, `qpdf`, `ghostscript`) and run:

```bash
python3 scripts/build_appimage.py
```

Download the current AppImage into the repository root before rebuilding.
The builder uses it as the seed for Flask/Pillow dependencies.
Its bundled Python version must match the build interpreter. Bundled dependency
licenses and source-package references are included inside the AppImage.

### Upgrading from an older version

Close the old OmniTool browser tab, download the latest AppImage, and replace
your previous copy. If you use a desktop shortcut or GNOME application launcher,
update it to point to the new file. Keep your existing `input`, `output`, `temp`,
and `watermark` folders; they do not need to be deleted during an upgrade.

OmniTool v3.2.0 uses port 5000 when available. If an older instance is still
running there, the new instance automatically reserves another local port and
opens its own URL. Check for **v3.2.0** and the actual address in the sidebar to
confirm which version is running.

If double-clicking opens an old version or does not launch correctly on Debian
GNOME, open a terminal in the folder containing the new AppImage and run:

```bash
chmod +x OmniTool-x86_64.AppImage
./OmniTool-x86_64.AppImage --appimage-extract-and-run
```

This starts the file directly and avoids FUSE mounting. The terminal prints the
version and address, for example `OmniTool v3.2.0 is running at
http://127.0.0.1:43293`. Use that address rather than an old bookmarked URL.
`Opening in existing browser session` means the system is reusing your browser
window; it does not mean an older OmniTool version has been launched.
