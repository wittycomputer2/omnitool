"""Offline, socket-free verification of the bundled application and native tools."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))


def main():
    with tempfile.TemporaryDirectory(prefix='omnitool-smoke-') as temporary:
        work = Path(temporary)
        os.environ['APPIMAGE'] = str(work / 'OmniTool.AppImage')
        import app
        from PIL import Image
        from tools import image_compressor, video_compressor, pdf_compressor
        for command in ('ffmpeg', 'ffprobe', 'qpdf', 'gs'):
            found = Path(shutil.which(command)).resolve()
            assert found == root / 'usr/bin' / command, (command, found)
            flag = '-version' if command in ('ffmpeg', 'ffprobe') else '--version'
            subprocess.run([str(found), flag], check=True, capture_output=True)
        assert Path(sys.executable).resolve() == root / 'usr/libexec' / f'python{sys.version_info.major}.{sys.version_info.minor}'
        input_dir, output_dir = work / 'input', work / 'output'
        events = []
        Image.new('RGBA', (100, 60), (10, 20, 30, 80)).save(input_dir / 'image.png', compress_level=0)
        image_compressor.run(input_dir, output_dir, {}, events.append)
        with Image.open(output_dir / 'image.png') as image:
            assert image.size == (100, 60)
            assert image.getpixel((0, 0)) == (10, 20, 30, 80)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=160x120:rate=10',
                        '-t', '1', '-c:v', 'mpeg4', '-q:v', '1', str(input_dir / 'video.mp4')], check=True)
        video_compressor.run(input_dir, output_dir, {}, events.append)
        assert (output_dir / 'video.mp4').exists()
        postscript = '%!PS\n/Helvetica findfont 18 scalefont setfont\n50 700 moveto (OmniTool PDF smoke test) show\nshowpage\n'
        subprocess.run(['gs', '-q', '-dNOPAUSE', '-dBATCH', '-sDEVICE=pdfwrite',
                        f'-sOutputFile={input_dir / "document.pdf"}', '-'], input=postscript, text=True, check=True)
        pdf_compressor.run(input_dir, output_dir, {}, events.append)
        assert (output_dir / 'document.pdf').exists()
        subprocess.run(['qpdf', '--check', str(output_dir / 'document.pdf')], check=True, capture_output=True)
        errors = [event for event in events if 'ERROR' in event.get('msg', '')]
        assert not errors, errors
        client = app.app.test_client()
        html = client.get('/', base_url='http://127.0.0.1:43210').get_data(as_text=True)
        assert 'v3.2.0' in html and 'Ready • 127.0.0.1:43210' in html
        assert 'Image Compression' in html and 'Video Compression' in html
        assert html.index('data-tool="image_compression"') < html.index('data-tool="video"')
        response = client.post('/api/move-output-to-input')
        assert response.json['ok'] and len(response.json['moved']) == 3, response.json
        assert len(client.get('/api/files').json) == 3
        print(json.dumps({'ok': True, 'version': app.APP_VERSION, 'python': sys.version.split()[0],
                          'bundled_tools': ['ffmpeg', 'ffprobe', 'qpdf', 'gs'],
                          'checks': ['image compression', 'video compression', 'PDF compression', 'UI rendering', 'move output to input']}))


if __name__ == '__main__':
    main()
