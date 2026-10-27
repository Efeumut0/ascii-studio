import tempfile
import unittest
from pathlib import Path

import av


class TestPublicFixtures(unittest.TestCase):
    def test_generated_clip_has_video_stereo_audio_and_expected_timing(self):
        from tools.make_test_media import make_clip

        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "generated.mp4"
            make_clip(video, frames=6, audio_duration=0.3, width=80, height=96)
            with av.open(str(video)) as container:
                self.assertEqual(container.streams.video[0].frames, 6)
                self.assertEqual(container.streams.video[0].width, 80)
                self.assertEqual(container.streams.audio[0].sample_rate, 44100)
                self.assertEqual(len(container.streams.audio[0].layout.channels), 2)
                self.assertAlmostEqual(container.duration / 1e6, 0.3, delta=0.025)
                self.assertEqual(len(list(container.decode(video=0))), 6)

    def test_generation_preserves_existing_file(self):
        from tools.make_test_media import make_clip

        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "existing.mp4"
            video.write_bytes(b"existing media")
            with self.assertRaises(FileExistsError):
                make_clip(video, frames=6, audio_duration=0.3, width=80, height=96)
            self.assertEqual(video.read_bytes(), b"existing media")
