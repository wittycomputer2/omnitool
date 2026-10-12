"""Regression checks for processing with optional renaming and reusing output."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image
import app as server
from tools import batch_rename, metadata_stripper, resizer


class FileWorkflowsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.input = Path(self.temp.name) / "input"
        self.output = Path(self.temp.name) / "output"
        self.input.mkdir()
        self.output.mkdir()
        self.events = []

    def image(self, name, color="red"):
        Image.new("RGB", (120, 60), color).save(self.input / name)

    def run_tool(self, tool, options):
        tool.run(self.input, self.output, options, self.events.append)
        self.assertFalse([e for e in self.events if "ERROR" in e.get("msg", "")], self.events)

    def test_resizer_defaults_to_fixed_dimensions(self):
        self.image("original.png")
        self.run_tool(resizer, {})
        with Image.open(self.output / "original.png") as image:
            self.assertEqual(image.size, (1920, 960))
        self.assertFalse((self.input / "original.png").exists())

    def test_percentage_still_works_without_renaming(self):
        self.image("original.png")
        self.run_tool(resizer, {"mode": "percentage", "target_size": 50, "rename_files": False, "prefix": "ignored"})
        with Image.open(self.output / "original.png") as image:
            self.assertEqual(image.size, (60, 30))

    def test_resize_and_rename_with_prefix_and_start_number(self):
        self.image("a.png")
        self.image("b.jpg")
        self.run_tool(resizer, {"target_size": 80, "rename_files": True, "prefix": "photo", "start_number": 7})
        self.assertEqual(sorted(f.name for f in self.output.iterdir()), ["photo_007.png", "photo_008.jpg"])
        for path in self.output.iterdir():
            with Image.open(path) as image:
                self.assertEqual(image.size, (80, 40))
        self.assertEqual(list(self.input.iterdir()), [])

    def test_convert_without_renaming(self):
        self.image("original.png")
        self.run_tool(metadata_stripper, {"rename_files": False, "prefix": "ignored"})
        self.assertTrue((self.output / "original.jpg").exists())

    def test_convert_and_rename_without_prefix(self):
        self.image("same.png")
        self.image("same.webp")
        self.run_tool(metadata_stripper, {"rename_files": True, "prefix": "", "start_number": 1})
        self.assertEqual(sorted(f.name for f in self.output.iterdir()), ["001.jpg", "002.jpg"])
        for path in self.output.iterdir():
            with Image.open(path) as image:
                self.assertEqual(image.format, "JPEG")
        self.assertEqual(list(self.input.iterdir()), [])

    def test_randomize_changes_number_assignment_for_both_tools(self):
        for tool in (resizer, metadata_stripper):
            with self.subTest(tool=tool.__name__):
                self.image("a.png", "red")
                self.image("b.png", "blue")
                with patch.object(batch_rename.random.SystemRandom, "shuffle", side_effect=lambda files: files.reverse()):
                    self.run_tool(tool, {"rename_files": True, "randomize_files": True, "prefix": "shuffled", "target_size": 120})
                first = self.output / ("shuffled_001.jpg" if tool is metadata_stripper else "shuffled_001.png")
                with Image.open(first) as image:
                    red, green, blue = image.getpixel((0, 0))
                    self.assertGreater(blue, red)
                for path in self.output.iterdir():
                    path.unlink()

    def test_optional_rename_keeps_existing_outputs(self):
        for tool in (resizer, metadata_stripper):
            with self.subTest(tool=tool.__name__):
                extension = ".jpg" if tool is metadata_stripper else ".png"
                existing = self.output / ("photo_001" + extension)
                existing.write_bytes(b"keep this")
                self.image("a.png")
                self.run_tool(tool, {"rename_files": True, "prefix": "photo", "target_size": 100})
                self.assertEqual(existing.read_bytes(), b"keep this")
                self.assertTrue((self.output / ("photo_001_1" + extension)).exists())

    def test_standalone_batch_rename_uses_shared_numbering(self):
        (self.input / "a.txt").write_text("first")
        (self.input / "b.txt").write_text("second")
        self.run_tool(batch_rename, {"prefix": "batch", "start_number": 999})
        self.assertEqual((self.output / "batch_0999.txt").read_text(), "first")
        self.assertEqual((self.output / "batch_1000.txt").read_text(), "second")
        self.assertEqual(list(self.input.iterdir()), [])

    def test_invalid_prefix_leaves_inputs_intact(self):
        self.image("a.png")
        for tool in (resizer, metadata_stripper):
            with self.assertRaises(ValueError):
                tool.run(self.input, self.output, {"rename_files": True, "prefix": "../escape"})
        self.assertTrue((self.input / "a.png").exists())
        self.assertEqual(list(self.output.iterdir()), [])

    def test_failed_and_unsupported_files_stay_in_input(self):
        self.image("good.png")
        (self.input / "bad.png").write_bytes(b"not an image")
        (self.input / "notes.txt").write_text("keep me")
        resizer.run(self.input, self.output, {"rename_files": True, "prefix": "photo", "target_size": 100}, self.events.append)
        self.assertTrue((self.input / "bad.png").exists())
        self.assertTrue((self.input / "notes.txt").exists())
        self.assertFalse((self.input / "good.png").exists())
        self.assertEqual(len(list(self.output.iterdir())), 1)

    def client(self):
        input_patch = patch.object(server, "INPUT_DIR", self.input)
        output_patch = patch.object(server, "OUTPUT_DIR", self.output)
        input_patch.start()
        output_patch.start()
        self.addCleanup(input_patch.stop)
        self.addCleanup(output_patch.stop)
        return server.app.test_client()

    def test_move_all_files_preserves_conflicts_and_folder_markers(self):
        client = self.client()
        (self.input / "same.jpg").write_bytes(b"original")
        (self.input / "same_1.jpg").write_bytes(b"also original")
        (self.output / "same.jpg").write_bytes(b"processed")
        (self.output / "empty.txt").touch()
        (self.output / ".hidden").write_bytes(b"hidden")
        (self.output / ".gitkeep").touch()
        response = client.post("/api/move-output-to-input")
        self.assertTrue(response.json["ok"])
        self.assertEqual(len(response.json["moved"]), 3)
        self.assertEqual((self.input / "same.jpg").read_bytes(), b"original")
        self.assertEqual((self.input / "same_2.jpg").read_bytes(), b"processed")
        self.assertTrue((self.input / "empty.txt").exists())
        self.assertEqual([f.name for f in self.output.iterdir()], [".gitkeep"])
        self.assertEqual(client.post("/api/move-output-to-input").json["moved"], [])

    def test_move_rejects_pending_and_running_jobs(self):
        client = self.client()
        (self.output / "a.txt").write_text("keep")
        with patch.object(server, "_pending_job", {"tool": "resizer"}):
            self.assertEqual(client.post("/api/move-output-to-input").status_code, 409)
        server._file_operation_lock.acquire()
        try:
            self.assertEqual(client.post("/api/move-output-to-input").status_code, 409)
        finally:
            server._file_operation_lock.release()
        self.assertTrue((self.output / "a.txt").exists())

    def test_process_stream_and_move_back_for_second_pass(self):
        client = self.client()
        self.image("original.png")
        response = client.post("/api/process", json={"tool": "resizer", "options": {"target_size": 80, "rename_files": True, "prefix": "photo"}})
        self.assertTrue(response.json["ok"])
        response = client.get("/api/stream")
        self.assertIn('"type": "done"', response.get_data(as_text=True))
        server._active_worker.join(timeout=5)
        self.assertFalse(server._file_operation_lock.locked())
        self.assertTrue(client.post("/api/move-output-to-input").json["ok"])
        self.run_tool(metadata_stripper, {})
        self.assertTrue((self.output / "photo_001.jpg").exists())
        self.assertEqual(list(self.input.iterdir()), [])

    def test_render_controls(self):
        html = server.app.test_client().get("/").get_data(as_text=True)
        self.assertIn('<option value="fixed" selected>', html)
        self.assertLess(html.index('id="moveFilesBtn"'), html.index('onclick="refreshFiles()"'))
        for tool in ("resizer", "metadata"):
            self.assertIn(f'id="{tool}-rename-enabled"', html)
            self.assertIn(f'id="{tool}-rename-fields" class="hidden', html)


if __name__ == "__main__":
    unittest.main()
