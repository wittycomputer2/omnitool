#!/usr/bin/env python3
"""Build OmniTool using an existing AppImage as the Python dependency seed.

Requires squashfs-tools, ffmpeg (including ffprobe), qpdf, and Ghostscript.
Bundles the interpreter, standard library, command-line tools, their shared
libraries, and a matching ELF loader so no system Python/media tools are needed.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=REPO / 'OmniTool-x86_64.AppImage')
    parser.add_argument('--output', type=Path, default=REPO / 'OmniTool-x86_64.AppImage')
    args = parser.parse_args()
    commands = {name: shutil.which(name) for name in ('mksquashfs', 'ffmpeg', 'ffprobe', 'qpdf', 'gs', 'ldd')}
    missing = [name for name, path in commands.items() if path is None]
    if missing:
        parser.error('Missing build tools: ' + ', '.join(missing))
    base = args.base.resolve()
    offset = int(subprocess.check_output([str(base), '--appimage-offset'], text=True).strip())
    with base.open('rb') as handle:
        runtime = handle.read(offset)
    with tempfile.TemporaryDirectory(prefix='omnitool-build-') as build_directory:
        build = Path(build_directory)
        subprocess.run([str(base), '--appimage-extract'], cwd=build, check=True, stdout=subprocess.DEVNULL)
        stage = build / 'squashfs-root'
        source = REPO / 'omnitool-v3'
        shutil.copy2(source / 'app.py', stage / 'app.py')
        for folder in ('tools', 'templates', 'static'):
            shutil.rmtree(stage / folder, ignore_errors=True)
            shutil.copytree(source / folder, stage / folder, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for folder in ('input', 'output', 'temp', 'watermark'):
            shutil.rmtree(stage / folder, ignore_errors=True)
        dependencies = stage / 'venv/lib' / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'site-packages'
        if not (dependencies / 'flask').exists():
            parser.error('Base AppImage must contain dependencies for the build Python version.')
        # pip and development launchers are unnecessary in the downloadable app.
        shutil.rmtree(stage / 'venv/bin', ignore_errors=True)
        for path in dependencies.glob('pip*'):
            if path.is_dir():
                shutil.rmtree(path)
        shutil.rmtree(stage / 'venv/include', ignore_errors=True)
        (stage / 'venv/pyvenv.cfg').unlink(missing_ok=True)
        usr = stage / 'usr'
        (usr / 'bin').mkdir(parents=True, exist_ok=True)
        (usr / 'libexec').mkdir(parents=True, exist_ok=True)
        (usr / 'lib').mkdir(parents=True, exist_ok=True)
        version = f'python{sys.version_info.major}.{sys.version_info.minor}'
        standard_library = Path(sys.base_prefix) / 'lib' / version
        shutil.copytree(standard_library, usr / 'lib' / version, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'test', 'tests', 'tkinter', 'idlelib', 'ensurepip'))
        python_binary = usr / 'libexec' / version
        shutil.copy2(Path(sys.executable).resolve(), python_binary)
        binaries = [python_binary]
        for name in ('ffmpeg', 'ffprobe', 'qpdf', 'gs'):
            binary = usr / 'libexec' / name
            shutil.copy2(commands[name], binary)
            binaries.append(binary)
            wrapper = usr / 'bin' / name
            wrapper.write_text('''#!/bin/sh
APPDIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
exec "$APPDIR/usr/lib/ld-linux-x86-64.so.2" --library-path "$APPDIR/usr/lib" "$APPDIR/usr/libexec/''' + name + '''" "$@"
''')
            wrapper.chmod(0o755)
        shutil.copy2(REPO / 'scripts/smoke_appimage.py', usr / 'libexec/smoke_appimage.py')
        # ldd includes transitive dependencies. Copy under the requested SONAME,
        # including libc and its loader; launch each tool with the bundled loader.
        libraries = set()
        for binary in binaries + list(dependencies.rglob('*.so')) + list((usr / 'lib' / version).rglob('*.so')):
            result = subprocess.run([commands['ldd'], str(binary)], capture_output=True, text=True)
            for match in re.finditer(r'(?:=>\s*)?(/[^\s]+)\s+\(', result.stdout):
                library = Path(match.group(1))
                if library.exists():
                    libraries.add(library)
            if 'not found' in result.stdout:
                raise RuntimeError(f'Missing library for {binary}: {result.stdout}')
        for library in libraries:
            shutil.copy2(library, usr / 'lib' / library.name)
        if not (usr / 'lib/ld-linux-x86-64.so.2').exists():
            raise RuntimeError('Build currently requires Linux x86_64.')
        # Ghostscript needs its initialization resources, not just libgs.
        shutil.copytree('/usr/share/ghostscript', usr / 'share/ghostscript', dirs_exist_ok=True)
        gs_versions = sorted(path.name for path in (usr / 'share/ghostscript').iterdir() if path.name[0].isdigit())
        gs_version = gs_versions[-1]
        # Include installed package copyright/license notices for bundled files.
        licenses = usr / 'share/doc/omnitool-bundled-licenses'
        licenses.mkdir(parents=True, exist_ok=True)
        bundled_files = [Path(sys.executable).resolve()] + [Path(commands[name]) for name in ('ffmpeg', 'ffprobe', 'qpdf', 'gs')] + list(libraries)
        packages = set()
        for path in bundled_files:
            result = subprocess.run(['dpkg-query', '-S', str(path.resolve())], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if ': ' in line:
                    packages.add(line.split(': ', 1)[0].split(':')[0])
        package_manifest = []
        for package in sorted(packages):
            copyright_file = Path('/usr/share/doc') / package / 'copyright'
            if copyright_file.exists():
                shutil.copy2(copyright_file, licenses / (package + '.copyright'))
            result = subprocess.run(['dpkg-query', '-W', '-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n', package], capture_output=True, text=True)
            fields = result.stdout.strip().split('\t')
            if result.returncode == 0 and len(fields) == 4:
                package_manifest.append({'package': fields[0], 'version': fields[1],
                                         'source_package': fields[2], 'source_version': fields[3],
                                         'source_url': f'https://sources.debian.org/src/{fields[2]}/{fields[3]}/'})
        (licenses / 'BUNDLED-PACKAGES.json').write_text(json.dumps(package_manifest, indent=2) + '\n')
        (stage / 'AppRun').write_text('''#!/bin/sh
set -eu
APPDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export APPDIR
export PATH="$APPDIR/usr/bin:$PATH"
export PYTHONHOME="$APPDIR/usr"
export PYTHONPATH="$APPDIR/venv/lib/''' + version + '''/site-packages"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export GS_LIB="$APPDIR/usr/share/ghostscript/''' + gs_version + '''/Resource/Init:$APPDIR/usr/share/ghostscript/''' + gs_version + '''/lib:$APPDIR/usr/share/ghostscript/''' + gs_version + '''/Resource:$APPDIR/usr/share/ghostscript/fonts"
cd "$APPDIR"
SCRIPT="app.py"
if [ "${1:-}" = "--self-test" ]; then
    SCRIPT="$APPDIR/usr/libexec/smoke_appimage.py"
    shift
fi
exec "$APPDIR/usr/lib/ld-linux-x86-64.so.2" --library-path "$APPDIR/usr/lib" "$APPDIR/usr/libexec/''' + version + '''" "$SCRIPT" "$@"
''')
        (stage / 'AppRun').chmod(0o755)
        (stage / 'BUILD-INFO.txt').write_text(f'OmniTool v3.2.0: Image Compression update\nPython: {sys.version}\nBundled: FFmpeg, FFprobe, QPDF, Ghostscript, Python and shared libraries\n')
        squashfs = build / 'payload.squashfs'
        subprocess.run([commands['mksquashfs'], str(stage), str(squashfs), '-noappend', '-comp', 'zstd', '-processors', '2', '-no-progress'], check=True, stdout=subprocess.DEVNULL)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=args.output.parent, prefix='.omnitool-build-', delete=False) as handle:
            assembled = Path(handle.name)
            handle.write(runtime)
            with squashfs.open('rb') as payload:
                shutil.copyfileobj(payload, handle)
        assembled.chmod(0o755)
        assembled.replace(args.output)
        print(f'Built {args.output} ({args.output.stat().st_size / 1048576:.1f} MB)')


if __name__ == '__main__':
    main()
