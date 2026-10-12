"""Exercise real encoders and confirm failures never remove original files."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, PngImagePlugin
import app as server
from tools import image_compressor, pdf_compressor, video_compressor


class CompressionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.input = Path(self.temp.name) / 'input'
        self.output = Path(self.temp.name) / 'output'
        self.input.mkdir()
        self.output.mkdir()
        self.events = []

    def run_tool(self, tool, options=None):
        tool.run(self.input, self.output, options or {}, self.events.append)
        self.assertFalse([event for event in self.events if 'ERROR' in event.get('msg', '')], self.events)

    def test_image_formats_dimensions_and_sizes(self):
        image = Image.new('RGB', (640, 320))
        image.putdata([((x * 17 + y * 3) % 256, x % 256, y % 256) for y in range(320) for x in range(640)])
        image.save(self.input / 'photo.jpg', quality=100, subsampling=0)
        image.save(self.input / 'photo.webp', lossless=True)
        alpha = Image.new('RGBA', (640, 320), (1, 2, 3, 64))
        alpha.save(self.input / 'alpha.png', compress_level=0)
        before = {path.name: path.stat().st_size for path in self.input.iterdir()}
        self.run_tool(image_compressor)
        self.assertEqual(list(self.input.iterdir()), [])
        for path in self.output.iterdir():
            self.assertLessEqual(path.stat().st_size, before[path.name])
            with Image.open(path) as output:
                self.assertEqual(output.size, (640, 320))
                if path.name == 'alpha.png':
                    self.assertEqual(output.getpixel((0, 0)), (1, 2, 3, 64))
        self.assertTrue(any('KB' in event.get('msg', '') and 'saved' in event.get('msg', '') for event in self.events))

    def test_lossless_webp_preserves_pixels_and_transparency(self):
        image = Image.new('RGBA', (90, 90), (123, 45, 67, 80))
        image.save(self.input / 'alpha.webp', lossless=True, method=0, exact=True)
        self.run_tool(image_compressor, {'lossless_webp': True})
        with Image.open(self.output / 'alpha.webp') as output:
            self.assertEqual(output.getpixel((0, 0)), (123, 45, 67, 80))

    def test_already_compressed_image_keeps_original_bytes(self):
        path = self.input / 'small.jpg'
        Image.new('RGB', (16, 16), 'red').save(path, quality=10, optimize=True)
        original = path.read_bytes()
        self.run_tool(image_compressor, {'quality': 100})
        self.assertEqual((self.output / path.name).read_bytes(), original)
        self.assertTrue(any('kept original bytes' in event.get('msg', '') for event in self.events))

    def test_metadata_toggle_and_orientation(self):
        for strip in (False, True):
            with self.subTest(strip=strip):
                image = Image.new('RGB', (120, 60), 'green')
                exif = Image.Exif()
                exif[274] = 6
                exif[315] = 'OmniTool test'
                image.save(self.input / 'orientation.jpg', quality=100, exif=exif)
                self.run_tool(image_compressor, {'quality': 80, 'strip_metadata': strip})
                with Image.open(self.output / 'orientation.jpg') as result:
                    self.assertEqual(result.size, (60, 120))
                    self.assertNotIn(274, result.getexif())
                    self.assertEqual(result.getexif().get(315), None if strip else 'OmniTool test')
                (self.output / 'orientation.jpg').unlink()

    def test_png_descriptive_metadata_toggle(self):
        for strip in (False, True):
            metadata = PngImagePlugin.PngInfo()
            metadata.add_text('Comment', 'keep if requested')
            Image.new('RGB', (100, 100), 'red').save(self.input / 'text.png', compress_level=0, pnginfo=metadata)
            self.run_tool(image_compressor, {'strip_metadata': strip})
            with Image.open(self.output / 'text.png') as image:
                self.assertEqual(image.info.get('Comment'), None if strip else 'keep if requested')
            (self.output / 'text.png').unlink()

    def test_animated_and_invalid_images_remain_in_input(self):
        frames = [Image.new('RGBA', (10, 10), color) for color in ('red', 'blue')]
        frames[0].save(self.input / 'animated.webp', save_all=True, append_images=frames[1:], duration=100, loop=0)
        (self.input / 'bad.jpg').write_bytes(b'not an image')
        (self.input / 'notes.txt').write_text('keep')
        image_compressor.run(self.input, self.output, {}, self.events.append)
        self.assertEqual(len(list(self.input.iterdir())), 3)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_existing_compressed_outputs_are_not_overwritten(self):
        existing = self.output / 'photo.png'
        existing.write_bytes(b'keep this')
        Image.new('RGB', (100, 100), 'red').save(self.input / 'photo.png', compress_level=0)
        self.run_tool(image_compressor)
        self.assertEqual(existing.read_bytes(), b'keep this')
        self.assertTrue((self.output / 'photo_1.png').exists())

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_real_video_preserves_audio_and_resolution(self):
        source = self.input / 'sample.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=12',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100', '-t', '1',
                        '-c:v', 'mpeg4', '-q:v', '1', '-c:a', 'aac', str(source)], check=True)
        original_size = source.stat().st_size
        before_audio = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(source), '-map', '0:a:0', '-c', 'copy', '-f', 'adts', '-'])
        self.run_tool(video_compressor)
        destination = self.output / 'sample.mp4'
        self.assertLessEqual(destination.stat().st_size, original_size)
        video = next(stream for stream in video_compressor.probe(destination) if stream['codec_type'] == 'video')
        self.assertEqual((video['width'], video['height']), (320, 240))
        self.assertEqual(video['codec_name'], 'h264')
        after_audio = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(destination), '-map', '0:a:0', '-c', 'copy', '-f', 'adts', '-'])
        self.assertEqual(before_audio, after_audio)

    def test_video_failed_encode_keeps_source_and_removes_partial_output(self):
        source = self.input / 'sample.mov'
        source.write_bytes(b'original video')
        def failed_encode(cmd, **kwargs):
            Path(cmd[-1]).write_bytes(b'partial')
            return subprocess.CompletedProcess(cmd, 1, '', 'encoding failed')
        with patch.object(video_compressor, 'probe', return_value=[{'codec_type': 'video'}]), patch.object(video_compressor.subprocess, 'run', side_effect=failed_encode):
            video_compressor.run(self.input, self.output, {}, self.events.append)
        self.assertEqual(source.read_bytes(), b'original video')
        self.assertEqual(list(self.output.iterdir()), [])

    def test_hdr_video_is_left_intact(self):
        source = self.input / 'hdr.mp4'
        source.write_bytes(b'original HDR')
        with patch.object(video_compressor, 'probe', return_value=[{'codec_type': 'video', 'color_transfer': 'smpte2084'}]):
            video_compressor.run(self.input, self.output, {}, self.events.append)
        self.assertTrue(source.exists())
        self.assertEqual(list(self.output.iterdir()), [])

    @staticmethod
    def pdf_fixture(path):
        # Simple uncompressed PDF with selectable text and a deliberately large stream.
        content = b'BT /F1 18 Tf 50 700 Td (OmniTool selectable text) Tj ET\n' + b'\n' * 20000
        objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
                   b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
                   b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
                   b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'endstream']
        data = bytearray(b'%PDF-1.4\n')
        offsets = [0]
        for index, obj in enumerate(objects, 1):
            offsets.append(len(data))
            data.extend(f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n')
        xref = len(data)
        data.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
        for offset in offsets[1:]:
            data.extend(f'{offset:010d} 00000 n \n'.encode())
        data.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
        path.write_bytes(data)

    @unittest.skipUnless(shutil.which('qpdf') and shutil.which('pdftotext') and shutil.which('pdftoppm'), 'PDF tools required')
    def test_real_pdf_preserves_text_and_rendered_page(self):
        source = self.input / 'document.pdf'
        self.pdf_fixture(source)
        original_size = source.stat().st_size
        before_text = subprocess.check_output(['pdftotext', str(source), '-'])
        before_pixels = subprocess.check_output(['pdftoppm', '-scale-to', '300', '-singlefile', str(source)])
        self.run_tool(pdf_compressor)
        destination = self.output / source.name
        self.assertLess(destination.stat().st_size, original_size)
        self.assertEqual(subprocess.check_output(['pdftotext', str(destination), '-']), before_text)
        self.assertEqual(subprocess.check_output(['pdftoppm', '-scale-to', '300', '-singlefile', str(destination)]), before_pixels)

    def test_pdf_error_retains_original_and_existing_output(self):
        source = self.input / 'bad.pdf'
        source.write_bytes(b'invalid PDF')
        existing = self.output / 'bad.pdf'
        existing.write_bytes(b'keep output')
        pdf_compressor.run(self.input, self.output, {}, self.events.append)
        self.assertEqual(source.read_bytes(), b'invalid PDF')
        self.assertEqual(existing.read_bytes(), b'keep output')
        self.assertEqual(list(self.output.iterdir()), [existing])

    def test_image_compression_ui_and_api(self):
        client = server.app.test_client()
        html = client.get('/').get_data(as_text=True)
        self.assertLess(html.index('data-tool="image_compression"'), html.index('data-tool="video"'))
        self.assertIn('Video Compression', html)
        self.assertIn('id="image-quality"', html)
        self.assertIn('id="image-lossless-webp"', html)
        with patch.object(server, '_pending_job', None):
            self.assertTrue(client.post('/api/process', json={'tool': 'image_compression', 'options': {'quality': 85}}).json['ok'])


if __name__ == '__main__':
    unittest.main()
