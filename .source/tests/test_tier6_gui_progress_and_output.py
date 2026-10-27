"""Tests for GUI progress messages and output folders."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame

import ascii_exporter
import ascii_gui
import ascii_video_renderer
from tests import PROJECT_ROOT, TEST_MP4_PATH


class TestTier6GuiProgressAndOutput(unittest.TestCase):
    """Test suite for GUI progress reporting and output folder structure."""

    @classmethod
    def setUpClass(cls):
        pygame.init()

    @classmethod
    def tearDownClass(cls):
        stray_dirs = [os.path.join(PROJECT_ROOT, "output", "2kedi")]
        for sd in stray_dirs:
            if os.path.exists(sd):
                shutil.rmtree(sd, ignore_errors=True)
        stray_files = [os.path.join(PROJECT_ROOT, "output", "test", "test_ascii.mp4")]
        for sf in stray_files:
            if os.path.exists(sf):
                try:
                    os.remove(sf)
                except OSError:
                    pass

    def test_01_sanitize_video_folder_name(self):
        """Verify video filename sanitization and folder name generation."""
        # 1. Standard video
        self.assertEqual(ascii_gui.sanitize_video_folder_name("asci.mp4"), "asci")
        self.assertEqual(ascii_gui.sanitize_video_folder_name("test.mp4"), "test")

        # 2. Complex title with spaces, Turkish characters, and double dots
        turkish_name = "Mentalist Türkçe Dublaj. Resmi dublaj..mp4"
        clean_tr = ascii_gui.sanitize_video_folder_name(turkish_name)
        self.assertIn("Mentalist", clean_tr)
        self.assertIn("Turkce", clean_tr)
        self.assertNotIn("ç", clean_tr)
        self.assertNotIn("ü", clean_tr)
        self.assertNotIn("..", clean_tr)

        # 3. Illegal Windows characters: <>:"/\|?*
        illegal_name = 'my<cool>:video*file?v1/sub\\name|extra".mp4'
        clean_illegal = ascii_gui.sanitize_video_folder_name(illegal_name)
        for ch in '<>:"/\\|?*':
            self.assertNotIn(ch, clean_illegal)

        # 4. Same logic in ascii_exporter and ascii_video_renderer
        self.assertEqual(
            ascii_exporter.sanitize_video_folder_name("test.mp4"),
            ascii_video_renderer.sanitize_video_folder_name("test.mp4"),
        )

        # 5. Output directory path resolution
        out_dir = ascii_gui.get_video_output_dir("test.mp4", "output")
        self.assertTrue(out_dir.endswith(os.path.join("output", "test")))
        self.assertTrue(os.path.isabs(out_dir))

    def test_02_cli_parsers_support_gui_progress_flag(self):
        """Verify CLI argument parsers for both exporter and renderer accept --gui-progress."""
        exp_parser = ascii_exporter.create_parser()
        exp_args = exp_parser.parse_args(["-i", "test.mp4", "--gui-progress"])
        self.assertTrue(exp_args.gui_progress)

        rend_parser = ascii_video_renderer.create_parser()
        rend_args = rend_parser.parse_args(["-i", "test.mp4", "--gui-progress"])
        self.assertTrue(rend_args.gui_progress)

    def test_03_ascii_video_renderer_default_output_folder(self):
        """Verify ascii_video_renderer defaults output to output/<video_name>/<video_name>_ascii.mp4."""
        out_dir = ascii_video_renderer.get_video_output_dir("my_clip.mp4", "output")
        expected = os.path.abspath(os.path.join("output", "my_clip"))
        self.assertEqual(out_dir, expected)

    def test_04_ascii_video_renderer_gui_progress_stream(self):
        """Verify ascii_video_renderer emits valid __PROGRESS_JSON__ stream during execution."""
        cmd = [
            sys.executable,
            "-u",
            os.path.join(PROJECT_ROOT, "ascii_video_renderer.py"),
            "-i", TEST_MP4_PATH,
            "--quality", "low",
            "--gui-progress",
            "--overwrite",
        ]

        proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, f"Renderer failed: {proc.stderr}")

        # Verify JSON lines in stdout
        json_lines = [
            line.split("__PROGRESS_JSON__", 1)[1]
            for line in proc.stdout.splitlines()
            if "__PROGRESS_JSON__" in line
        ]
        self.assertGreater(len(json_lines), 5, "Expected multiple progress JSON updates")

        progress_updates = [json.loads(line) for line in json_lines if "pct" in line]
        self.assertGreater(len(progress_updates), 0)

        # Verify fields in updates
        first_up = progress_updates[0]
        self.assertIn("pct", first_up)
        self.assertIn("current", first_up)
        self.assertIn("total", first_up)
        self.assertIn("fps", first_up)
        self.assertIn("eta", first_up)
        self.assertIn("bar", first_up)
        self.assertIn("text", first_up)
        self.assertIn("stage", first_up)

        # Verify done message
        done_msgs = [json.loads(line) for line in json_lines if '"type": "done"' in line]
        self.assertEqual(len(done_msgs), 1)
        self.assertTrue(done_msgs[0]["success"])
        self.assertIn("output", done_msgs[0])
        self.assertTrue(os.path.exists(done_msgs[0]["output"]))

    def test_05_ascii_exporter_gui_progress_stream(self):
        """Verify ascii_exporter emits valid __PROGRESS_JSON__ stream during export."""
        with tempfile.TemporaryDirectory() as td:
            target_out = os.path.join(td, "export_test")
            cmd = [
                sys.executable,
                "-u",
                os.path.join(PROJECT_ROOT, "ascii_exporter.py"),
                "-i", TEST_MP4_PATH,
                "-o", target_out,
                "--quality", "low",
                "--overwrite",
                "--gui-progress",
            ]

            proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0, f"Exporter failed: {proc.stderr}")

            json_lines = [
                line.split("__PROGRESS_JSON__", 1)[1]
                for line in proc.stdout.splitlines()
                if "__PROGRESS_JSON__" in line
            ]
            self.assertGreater(len(json_lines), 3)

            progress_updates = [json.loads(line) for line in json_lines if "pct" in line]
            self.assertGreater(len(progress_updates), 0)
            self.assertIn("pct", progress_updates[0])
            self.assertIn("current", progress_updates[0])
            self.assertIn("fps", progress_updates[0])

            done_msgs = [json.loads(line) for line in json_lines if '"type": "done"' in line]
            self.assertEqual(len(done_msgs), 1)
            self.assertTrue(done_msgs[0]["success"])

    def test_06_ascii_gui_initialization_and_buttons(self):
        """Verify AsciiStudioGui initializes with all 4 action buttons and renders properly."""
        gui = ascii_gui.AsciiStudioGui(width=940, height=680)
        self.assertIsNotNone(gui.screen)
        gui.draw()

        # Check all 4 primary action buttons are registered
        self.assertIn("PLAY", gui.rendered_buttons)
        self.assertIn("RENDER", gui.rendered_buttons)
        self.assertIn("EXPORT", gui.rendered_buttons)
        self.assertIn("QUIT", gui.rendered_buttons)

    def test_07_ascii_gui_drop_file_handling(self):
        """Verify drag-and-drop file handling in AsciiStudioGui."""
        gui = ascii_gui.AsciiStudioGui(width=940, height=680)
        initial_count = len(gui.videos)

        # Drop existing test.mp4
        gui.handle_drop_file(os.path.abspath(TEST_MP4_PATH))
        self.assertGreaterEqual(len(gui.videos), initial_count)
        selected_vid = gui.videos[gui.selected_video_idx]
        self.assertEqual(os.path.basename(selected_vid["path"]), "test.mp4")

        # Drop invalid non-video file
        with tempfile.NamedTemporaryFile(suffix=".txt") as tf:
            gui.handle_drop_file(tf.name)
            self.assertIn("[UYARI]", gui.status_message)

    def test_08_ascii_gui_worker_queue_polling_and_modals(self):
        """Verify worker queue polling updates GUI state, percentage, and modal transitions."""
        gui = ascii_gui.AsciiStudioGui(width=940, height=680)
        gui.is_busy = True
        gui.active_task = "render"
        gui.active_video_name = "test.mp4"
        gui.active_target_folder = "output/test"

        # 1. Enqueue progress message
        gui.progress_queue.put(("progress", {
            "pct": 65.4,
            "current": 205,
            "total": 314,
            "fps": 48.2,
            "eta": 2.3,
            "bar": "████████░░░░░░░░",
            "text": "[████████░░░░░░░░] 65.4% (205/314) | 48.2 FPS | ETA: 2.3s",
            "stage": "Video Kareleri İşleniyor (205/314)",
        }))

        gui.poll_worker_queue()
        self.assertEqual(gui.progress_pct, 65.4)
        self.assertEqual(gui.progress_current, 205)
        self.assertEqual(gui.progress_total, 314)
        self.assertEqual(gui.progress_fps, 48.2)
        self.assertEqual(gui.progress_eta, 2.3)
        self.assertIn("65.4%", gui.progress_bar_text)

        # Test draw with active busy modal
        gui.draw()

        # 2. Enqueue completion message
        gui.progress_queue.put(("done", {
            "success": True,
            "target_folder": os.path.abspath("output/test"),
            "task": "render",
        }))

        gui.poll_worker_queue()
        self.assertFalse(gui.is_busy)
        self.assertTrue(gui.show_completion_modal)
        self.assertTrue(gui.completion_success)

        # Test draw with completion modal
        gui.draw()
        self.assertIn("OPEN_FOLDER", gui.modal_buttons)
        self.assertIn("CLOSE_MODAL", gui.modal_buttons)

        # Test closing completion modal
        gui.handle_click(gui.modal_buttons["CLOSE_MODAL"].center)
        self.assertFalse(gui.show_completion_modal)

    def test_09_ascii_exporter_default_output_dir_resolution(self):
        """Verify ascii_exporter defaults output to output/<video_name>/ when -o is omitted."""
        parser = ascii_exporter.create_parser()
        args = parser.parse_args(["-i", "test.mp4"])
        self.assertIsNone(args.output, "Default output argument in parser must be None so export_video can resolve output/<video_name>/")

        # Test output directory resolver directly
        out_dir = ascii_exporter.get_video_output_dir("test.mp4", "output")
        self.assertTrue(out_dir.endswith(os.path.join("output", "test")))
        self.assertTrue(os.path.isabs(out_dir))

    def test_10_ascii_exporter_progress_monotonicity(self):
        """Verify ascii_exporter JSON progress values are strictly monotonic and within 0..100%."""
        with tempfile.TemporaryDirectory() as td:
            target_out = os.path.join(td, "monotonic_test")
            cmd = [
                sys.executable,
                "-u",
                os.path.join(PROJECT_ROOT, "ascii_exporter.py"),
                "-i", TEST_MP4_PATH,
                "-o", target_out,
                "--quality", "low",
                "--overwrite",
                "--gui-progress",
            ]

            proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0, f"Exporter failed: {proc.stderr}")

            pct_values = []
            for line in proc.stdout.splitlines():
                if "__PROGRESS_JSON__" in line:
                    data = json.loads(line.split("__PROGRESS_JSON__", 1)[1])
                    if "pct" in data:
                        pct_values.append(data["pct"])

            self.assertGreater(len(pct_values), 3)
            # Ensure each percentage is non-decreasing and bounded [0, 100]
            for i in range(len(pct_values)):
                self.assertGreaterEqual(pct_values[i], 0.0)
                self.assertLessEqual(pct_values[i], 100.0)
                if i > 0:
                    self.assertGreaterEqual(
                        pct_values[i],
                        pct_values[i - 1],
                        f"Progress jumped backwards from {pct_values[i-1]}% to {pct_values[i]}%!",
                    )

    def test_11_internal_drag_and_drop_interaction(self):
        """Verify internal drag-and-drop gesture from video list onto EXPORT and RENDER buttons."""
        gui = ascii_gui.AsciiStudioGui(width=940, height=680)
        gui.videos = [{"name": "test.mp4", "path": os.path.abspath(TEST_MP4_PATH), "size_str": "660 KB"}]
        gui.draw()

        self.assertGreater(len(gui.videos), 0)
        # Select first video
        first_rect = gui.rendered_video_rects[0][1]

        # 1. Mouse down on first video item
        gui.handle_click(first_rect.center)
        self.assertEqual(gui.selected_video_idx, 0)
        self.assertEqual(gui.dragging_video_idx, 0)
        self.assertFalse(gui.is_dragging_video)

        # 2. Mouse move beyond threshold
        drag_pos = (first_rect.centerx + 40, first_rect.centery + 40)
        gui.handle_mouse_move(drag_pos)
        self.assertTrue(gui.is_dragging_video)

        # 3. Test draw while dragging
        gui.draw()

        # 4. Release mouse over RENDER button
        render_btn_rect = gui.rendered_buttons["RENDER"]
        gui.handle_mouse_up(render_btn_rect.center)
        self.assertFalse(gui.is_dragging_video)
        self.assertEqual(gui.dragging_video_idx, -1)
        self.assertTrue(gui.is_busy)
        self.assertEqual(gui.active_task, "render")

    def test_12_open_folder_suppression_in_test_mode(self):
        """Verify open_folder_in_explorer safely returns without spawning explorer when SDL dummy is active."""
        # Under dummy driver (set at top of test module), this should be a silent no-op
        ascii_gui.open_folder_in_explorer("output/test")


if __name__ == "__main__":
    unittest.main()
