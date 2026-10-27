import contextlib
import io
import json
import os
import queue
import subprocess
import sys
import tempfile
import time
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["ASCII_TEST_MODE"] = "1"

import av
import numpy as np

import ascii_exporter
import ascii_gui
import ascii_player
import ascii_video_renderer
from ascii_engine.video_decoder import VideoDecoder

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestAuditRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / "source.mp4"
        with av.open(str(self.video), "w") as container:
            stream = container.add_stream("libx264", rate=12)
            stream.width = 64
            stream.height = 48
            stream.pix_fmt = "yuv420p"
            for frame_number in range(12):
                pixels = np.full((48, 64, 3), frame_number * 20, dtype=np.uint8)
                frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)

    def test_export_fps_cap_samples_frames_and_preserves_duration(self):
        with contextlib.redirect_stdout(io.StringIO()):
            folder = ascii_exporter.export_video(
                str(self.video), str(self.root / "export"), fps=6, audio=False,
            )
        config = json.loads((Path(folder) / "config.json").read_text())
        with np.load(Path(folder) / "ascii_data.npz") as data:
            self.assertEqual(data["chars"].shape[0], 6)
            brightness = data["colors"][:, 0, 0, 0].tolist()
            self.assertTrue(all(abs(actual - expected) < 5 for actual, expected in
                                zip(brightness, [0, 40, 80, 120, 160, 200])))
        self.assertEqual(config["fps"], 6)
        self.assertAlmostEqual(config["total_frames"] / config["fps"], 1.0)

    def test_render_fps_changes_preserve_video_duration(self):
        for rate in (6, 24, 7.5):
            with self.subTest(rate=rate):
                output = self.root / f"render_{rate}.mp4"
                ascii_video_renderer.render_video_to_mp4(
                    str(self.video), str(output), cols=20, font_size=6,
                    resolution="original", fps=rate, audio=False, workers=1,
                )
                with av.open(str(output)) as container:
                    stream = container.streams.video[0]
                    self.assertEqual(stream.average_rate, Fraction(str(rate)))
                    self.assertAlmostEqual(float(stream.duration * stream.time_base), 1.0, delta=1 / rate)
                    self.assertEqual(sum(1 for _ in container.decode(stream)), int(np.ceil(rate)))

    def test_renderer_rejects_output_that_would_overwrite_source(self):
        original = self.video.read_bytes()
        with self.assertRaises(ValueError):
            ascii_video_renderer.render_video_to_mp4(
                str(self.video), str(self.video), cols=20, font_size=6,
                resolution="original", audio=False, workers=1,
            )
        self.assertEqual(self.video.read_bytes(), original)

    def test_renderer_rejects_video_with_no_decodable_frames(self):
        with patch.object(VideoDecoder, "iter_frames", return_value=iter(())), self.assertRaises(ValueError):
            ascii_video_renderer.render_video_to_mp4(
                str(self.video), str(self.root / "empty.mp4"), cols=20,
                font_size=6, resolution="original", audio=False, workers=1,
            )

    def test_gui_worker_emits_one_completion_after_process_exit(self):
        gui = ascii_gui.AsciiStudioGui.__new__(ascii_gui.AsciiStudioGui)
        gui.progress_queue = queue.Queue()
        child = "import json; print('__PROGRESS_JSON__' + json.dumps({'type':'done','success':True,'folder':'result'}))"
        gui._run_subprocess_worker([sys.executable, "-c", child], "fallback", "render")
        messages = list(gui.progress_queue.queue)
        completions = [payload for kind, payload in messages if kind == "done"]
        self.assertEqual(len(completions), 1)
        self.assertEqual(completions[0]["target_folder"], "result")
        self.assertEqual(completions[0]["returncode"], 0)

    def test_standalone_rejects_malformed_data_without_traceback(self):
        for chars, colors in ((np.zeros(2), np.zeros(2)),
                              (np.zeros((2, 3, 4), dtype=np.uint8), np.zeros((1, 3, 4, 3), dtype=np.uint8))):
            with self.subTest(shape=chars.shape):
                np.savez(self.root / "data.npz", chars=chars, colors=colors)
                config = self.root / "config.json"
                config.write_text(json.dumps({"data_file": "data.npz", "fps": 12}))
                result = subprocess.run(
                    [sys.executable, str(PROJECT_ROOT / "standalone_template" / "run.py"),
                     "--config", str(config), "--headless", "--duration", "0.1"],
                    capture_output=True, timeout=10, check=False,
                )
                self.assertEqual(result.returncode, 1)
                self.assertNotIn(b"Traceback", result.stderr)

    def test_decoder_rejects_ramps_that_overflow_uint8(self):
        with self.assertRaises(ValueError), VideoDecoder(str(self.video), char_ramp="@" * 257):
            pass

    def test_standalone_rejects_invalid_config_without_traceback(self):
        for config_data in ([], {"fps": "invalid"}, {"fps": 0}, {"fps": float("nan")}):
            with self.subTest(config=config_data):
                config = self.root / "config.json"
                config.write_text(json.dumps(config_data))
                result = subprocess.run(
                    [sys.executable, str(PROJECT_ROOT / "standalone_template" / "run.py"),
                     "--config", str(config), "--headless", "--duration", "0.1"],
                    capture_output=True, timeout=10, check=False,
                )
                self.assertEqual(result.returncode, 1)
                self.assertNotIn(b"Traceback", result.stderr)
                self.assertIn(b"config", result.stdout.lower())

    def test_live_player_finishes_when_audio_is_shorter_than_video(self):
        video = self.root / "short_audio.mp4"
        with av.open(str(video), "w") as container:
            video_stream = container.add_stream("libx264", rate=12)
            video_stream.width = 64
            video_stream.height = 48
            video_stream.pix_fmt = "yuv420p"
            audio_stream = container.add_stream("aac", rate=44100)
            audio_stream.layout = "stereo"
            for _ in range(12):
                frame = av.VideoFrame.from_ndarray(np.zeros((48, 64, 3), dtype=np.uint8), format="rgb24")
                for packet in video_stream.encode(frame):
                    container.mux(packet)
            for packet in video_stream.encode():
                container.mux(packet)
            audio_frame = av.AudioFrame.from_ndarray(np.zeros((2, 11025), dtype=np.float32),
                                                    format="fltp", layout="stereo")
            audio_frame.sample_rate = 44100
            for packet in audio_stream.encode(audio_frame):
                container.mux(packet)
            for packet in audio_stream.encode():
                container.mux(packet)
        started = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            ascii_player.play_video(str(video), cols=20, headless=True, max_duration=3.0)
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 2.7, "Player waited for runtime limit instead of finishing video")

    def test_encoder_failure_does_not_deadlock_with_full_queue(self):
        result = subprocess.run(
            [sys.executable, "-m", "tests.test_audit_regressions", "--encoder-failure", str(self.video)],
            cwd=PROJECT_ROOT, capture_output=True, timeout=12, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))


def exercise_encoder_failure(video_path):
    import time

    real_open = av.open
    real_queue = queue.Queue

    class BrokenStream:
        def encode(self, *args):
            time.sleep(0.3)
            raise RuntimeError("injected encoder failure")

    class BrokenOutput:
        def add_stream(self, *args, **kwargs):
            return BrokenStream()

        def close(self):
            pass

    def open_container(path, *args, **kwargs):
        if kwargs.get("mode") == "w":
            return BrokenOutput()
        return real_open(path, *args, **kwargs)

    with patch.object(av, "open", side_effect=open_container), \
            patch.object(queue, "Queue", side_effect=lambda **kwargs: real_queue(maxsize=1)):
        try:
            ascii_video_renderer.render_video_to_mp4(
                video_path, video_path + ".out.mp4", cols=20, font_size=6,
                resolution="original", audio=False, workers=1,
            )
        except RuntimeError as exc:
            if str(exc) == "injected encoder failure":
                return
            raise
        raise AssertionError("Encoder failure was swallowed")


if __name__ == "__main__":
    if "--encoder-failure" in sys.argv:
        exercise_encoder_failure(sys.argv[-1])
    else:
        unittest.main()
