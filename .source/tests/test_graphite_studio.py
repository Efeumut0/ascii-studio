import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from studio.model import StudioSettings, application_paths, load_settings, save_settings


class TestStudioModel(unittest.TestCase):
    def test_defaults_match_requested_playback(self):
        settings = StudioSettings()
        self.assertTrue(settings.audio)
        self.assertFalse(settings.crt)
        self.assertFalse(settings.loop)
        self.assertFalse(settings.hud)
        self.assertEqual(settings.language, "tr")

    def test_all_settings_survive_persistence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            settings = StudioSettings(language="en", quality="15", cols=380, fps=24,
                                      resolution="4k", seek_step=30, audio=False)
            save_settings(path, settings)
            self.assertEqual(load_settings(path), settings)

    def test_invalid_settings_are_rejected(self):
        for changes in ({"cols": 1}, {"fps": float("nan")}, {"char_ramp": "@" * 257},
                        {"workers": -1}, {"language": "invalid"}, {"char_aspect": 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                StudioSettings(**changes).validate()

    def test_corrupt_settings_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            path.write_text(json.dumps({"fps": "invalid"}))
            self.assertEqual(load_settings(path), StudioSettings())

    def test_paths_depend_on_executable_location_not_working_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = application_paths(Path(folder))
            self.assertEqual(paths["output"], Path(folder).resolve() / "output")
            self.assertEqual(paths["videos"], Path(folder).resolve() / "videos")


class TestGraphiteWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from studio.window import StudioWindow
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.window = StudioWindow(root=Path(self.temp.name))
        self.addCleanup(self.window.close)

    def test_language_switch_updates_labels_without_losing_settings(self):
        self.window.quality.setCurrentIndex(14)
        self.window.set_language("en")
        self.assertEqual(self.window.heading.text(), "Files and output")
        self.assertEqual(self.window.render_button.text(), "Create MP4")
        self.assertEqual(self.window.quality.currentData(), "15")
        self.window.set_language("tr")
        self.assertEqual(self.window.render_button.text(), "MP4 oluştur")

    def test_advanced_settings_round_trip(self):
        dialog = self.window.create_advanced_dialog()
        dialog.controls["cols"].setValue(300)
        dialog.controls["seek_step"].setValue(30)
        dialog.controls["char_ramp"].setText(" .:#@")
        dialog.controls["crf"].setValue(18)
        self.window.set_language("en")
        self.assertEqual(dialog.controls["cols"].value(), 300)
        self.assertEqual(dialog.tabs.tabText(1), "Playback")
        dialog.apply_settings()
        self.assertEqual(self.window.settings.cols, 300)
        self.assertEqual(self.window.settings.seek_step, 30)
        self.assertEqual(self.window.settings.char_ramp, " .:#@")
        self.assertEqual(self.window.settings.crf, 18)
        dialog.close()

    def test_native_file_selection_and_all_presets(self):
        video = Path(self.temp.name) / "sample.mp4"
        video.write_bytes(b"sample")
        self.window.add_files([str(video)])
        self.assertEqual(self.window.table.rowCount(), 1)
        self.assertEqual(self.window.selected_video(), video.resolve())
        self.assertEqual(self.window.quality.count(), 15)

    def test_video_row_hover_updates_without_scrolling_and_clears_on_leave(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtTest import QTest

        for name in ("first.mp4", "second.mp4", "third.mp4"):
            path = Path(self.temp.name) / name
            path.write_bytes(b"video")
            self.window.add_files([path])
        self.window.resize(1048, 740)
        self.window.show()
        self.app.processEvents()
        table = self.window.table
        rectangle = table.visualItemRect(table.item(1, 0))
        QTest.mouseMove(table.viewport(), rectangle.center())
        self.app.processEvents()
        self.assertEqual(table.hovered_row, 1)
        hover_image = table.viewport().grab().toImage()
        self.app.sendEvent(table.viewport(), QEvent(QEvent.Type.Leave))
        self.app.processEvents()
        self.assertEqual(table.hovered_row, -1)
        self.assertNotEqual(hover_image, table.viewport().grab().toImage())

    def test_window_corners_are_transparent_and_content_remains_opaque(self):
        self.window.show()
        self.app.processEvents()
        image = self.window.grab().toImage()
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        self.assertEqual(image.pixelColor(image.width() // 2, 20).alpha(), 255)

    def test_video_selection_uses_bottom_of_row(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest

        for name in ("first.mp4", "second.mp4"):
            path = Path(self.temp.name) / name
            path.write_bytes(b"video")
            self.window.add_files([path])
        self.window.show()
        self.app.processEvents()
        self.window.table.selectRow(0)
        rectangle = self.window.table.visualItemRect(self.window.table.item(1, 0))
        QTest.mouseClick(self.window.table.viewport(), Qt.MouseButton.LeftButton,
                         pos=QPoint(rectangle.center().x(), rectangle.bottom() - 3))
        self.assertEqual(self.window.selected_video().name, "second.mp4")

    def test_hover_follows_scroll_and_clears_over_empty_space(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtTest import QTest

        for index in range(20):
            path = Path(self.temp.name) / f"video-{index}.mp4"
            path.write_bytes(b"video")
            self.window.add_files([path])
        self.window.show()
        self.app.processEvents()
        table = self.window.table
        table.scrollToTop()
        point = table.visualItemRect(table.item(1, 0)).center()
        QTest.mouseMove(table.viewport(), point)
        table.verticalScrollBar().setValue(2)
        self.app.processEvents()
        self.assertEqual(table.hovered_row, table.indexAt(point).row())
        table.setRowCount(1)
        table.scrollToTop()
        QTest.mouseMove(table.viewport(), QPoint(2, table.viewport().height() - 1))
        self.app.processEvents()
        self.assertEqual(table.hovered_row, -1)

    def test_maximized_window_has_square_corners_then_rounds_after_restore(self):
        self.window.showMaximized()
        self.app.processEvents()
        self.assertEqual(self.window.grab().toImage().pixelColor(0, 0).alpha(), 255)
        self.window.showNormal()
        self.app.processEvents()
        self.assertEqual(self.window.grab().toImage().pixelColor(0, 0).alpha(), 0)

    def test_job_request_contains_advanced_values_and_main_toggles(self):
        video = Path(self.temp.name) / "sample.mp4"
        video.write_bytes(b"sample")
        self.window.add_files([str(video)])
        self.window.audio.setChecked(False)
        self.window.crt.setChecked(True)
        self.window.settings.cols = 250
        request = self.window.make_request("render")
        self.assertFalse(request["settings"]["audio"])
        self.assertTrue(request["settings"]["crt"])
        self.assertEqual(request["settings"]["cols"], 250)
        self.assertEqual(Path(request["output"]).parent.name, "sample")

    def test_gui_starts_worker_and_unlocks_only_after_artifact_exists(self):
        from PySide6.QtTest import QTest

        source = Path(__file__).resolve().parents[1] / "test.mp4"
        self.window.add_files([source])
        self.window.settings.cols = 20
        self.window.settings.resolution = "original"
        self.window.apply_settings_to_controls()
        self.window.audio.setChecked(False)
        self.window.start_job("render")
        self.assertFalse(self.window.render_button.isEnabled())
        for _ in range(600):
            QTest.qWait(50)
            if self.window.process is None:
                break
        self.assertIsNone(self.window.process)
        self.assertTrue(Path(self.window.active_request["output"]).is_file())
        self.assertEqual(self.window.progress.value(), 1000)
        self.assertTrue(self.window.render_button.isEnabled())

    def test_cancelling_worker_never_publishes_partial_output(self):
        from PySide6.QtTest import QTest

        source = Path(__file__).resolve().parents[1] / "test.mp4"
        self.window.add_files([source])
        self.window.start_job("render")
        self.window.cancel_job()
        for _ in range(100):
            QTest.qWait(50)
            if self.window.process is None:
                break
        self.assertIsNone(self.window.process)
        self.assertFalse(Path(self.window.active_request["output"]).exists())
        self.assertEqual(self.window.last_stage, "cancelled")


class TestPortableExport(unittest.TestCase):
    def test_exported_arrays_have_selected_density_and_audio_is_omitted(self):
        import zipfile

        import numpy as np

        from studio.portable import export_portable

        source = Path(__file__).resolve().parents[1] / "test.mp4"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stub = root / "stub.exe"
            stub.write_bytes(b"MZ-test-stub")
            output = root / "test.exe"
            events = []
            export_portable(source, output, StudioSettings(cols=20, audio=False, fps=12),
                            stub, lambda **event: events.append(event))
            with zipfile.ZipFile(output) as archive:
                self.assertNotIn("audio.wav", archive.namelist())
                config = json.loads(archive.read("config.json"))
                self.assertEqual(config["cols"], 20)
                self.assertEqual(config["fps"], 12)
                self.assertFalse(config["audio_enabled"])
                self.assertFalse(config["show_hud"])
                with archive.open("chars.npy") as chars:
                    data = np.load(chars)
                    self.assertEqual(data.shape[2], 20)
                    self.assertGreater(data.shape[0], 120)
            self.assertEqual(events[-1]["percent"], 100)
            with zipfile.ZipFile(output) as archive:
                archive.extractall(root / "unpacked")
            result = subprocess.run(
                [sys.executable, str(source.parent / "standalone_template" / "run.py"),
                 "--config", str(root / "unpacked" / "config.json"), "--headless", "--duration", "0.1"],
                capture_output=True, timeout=15, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_export_failure_preserves_existing_output(self):
        from studio.portable import export_portable
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "existing.exe"
            output.write_bytes(b"previous output")
            with self.assertRaises(FileNotFoundError):
                export_portable(Path(folder) / "missing.mp4", output, StudioSettings(),
                                Path(folder) / "missing-stub.exe", lambda **event: None)
            self.assertEqual(output.read_bytes(), b"previous output")

    def test_worker_applies_render_settings_and_returns_playable_video(self):
        from dataclasses import asdict

        import av
        source_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            request = {"action": "render", "video": str(source_root / "test.mp4"),
                       "output": str(root / "result.mp4"), "progress": str(root / "progress.json"),
                       "log": str(root / "worker.log"),
                       "settings": asdict(StudioSettings(cols=20, audio=False, fps=12,
                                                         resolution="original", crf=28))}
            path = root / "request.json"
            path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(source_root / "studio_main.py"), "--worker", str(path)],
                                    capture_output=True, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, (root / "worker.log").read_text(encoding="utf-8"))
            progress = json.loads((root / "progress.json").read_text())
            self.assertTrue(progress["success"])
            with av.open(str(root / "result.mp4")) as container:
                self.assertEqual(len(container.streams.audio), 0)
                self.assertEqual(float(container.streams.video[0].average_rate), 12)


if __name__ == "__main__":
    unittest.main()
