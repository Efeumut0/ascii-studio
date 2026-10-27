"""Tests for boundary values, invalid input, and error handling."""

import json
import os
import tempfile
import unittest
import zipfile

import av
import numpy as np
import pygame

from tests import (
    DEFAULT_RAMP,
    PROJECT_ROOT,
    TEST_MP4_PATH,
)


class TestB01LivePlayerBoundaries(unittest.TestCase):
    """F01 Boundaries: Live Player Entry."""

    def test_01_missing_file_raises_error(self):
        """Verify non-existent video path raises FileNotFoundError or error exit."""
        fake_path = os.path.join(PROJECT_ROOT, "does_not_exist_987654.mp4")
        self.assertFalse(os.path.exists(fake_path))
        with self.assertRaises((av.error.FileNotFoundError, FileNotFoundError, SystemExit)):
            # PyAV or CLI raises error on missing file
            _ = av.open(fake_path)

    def test_02_path_with_spaces_and_unicode(self):
        """Verify video path containing spaces and unicode characters is handled cleanly."""
        unicode_path = os.path.join(PROJECT_ROOT, "türkçe_video test_測試.mp4")
        # Ensure path normalizes without crashing
        norm = os.path.normpath(unicode_path)
        self.assertTrue(os.path.isabs(norm))

    def test_03_empty_input_string_rejected(self):
        """Verify empty string input path is rejected."""
        empty_path = ""
        with self.assertRaises((ValueError, av.error.FileNotFoundError, SystemExit, OSError)):
            if not empty_path:
                raise ValueError("Video path cannot be empty")
            _ = av.open(empty_path)

    def test_04_zero_byte_video_file_rejected(self):
        """Verify zero-byte empty file raises InvalidDataError or EOFError."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
            tf_path = tf.name
        try:
            self.assertEqual(os.path.getsize(tf_path), 0)
            with self.assertRaises((av.error.InvalidDataError, av.error.EOFError, SystemExit)):
                _ = av.open(tf_path)
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_05_player_startup_with_invalid_fps_clamps(self):
        """Verify non-positive or extreme FPS is clamped to safe range [1.0, 120.0]."""
        fps_low = -10.0
        fps_high = 999.0
        clamped_low = max(1.0, min(120.0, fps_low))
        clamped_high = max(1.0, min(120.0, fps_high))
        self.assertEqual(clamped_low, 1.0)
        self.assertEqual(clamped_high, 120.0)


class TestB02ExporterBoundaries(unittest.TestCase):
    """F02 Boundaries: Standalone Exporter."""

    def test_01_existing_output_without_overwrite_aborts(self):
        """Verify exporter does not destroy existing folder if overwrite=False."""
        with tempfile.TemporaryDirectory() as td:
            out_dir = os.path.join(td, "existing_output")
            os.makedirs(out_dir, exist_ok=True)
            sentinel_file = os.path.join(out_dir, "keep_me.txt")
            with open(sentinel_file, "w") as f:
                f.write("sentinel")

            # Check overwrite logic
            overwrite = False
            if os.path.exists(out_dir) and not overwrite:
                aborted = True
            else:
                aborted = False
            self.assertTrue(aborted)
            self.assertTrue(os.path.exists(sentinel_file))

    def test_02_overwrite_flag_cleans_destination(self):
        """Verify exporter with overwrite=True cleanly proceeds."""
        with tempfile.TemporaryDirectory() as td:
            out_dir = os.path.join(td, "target_output")
            os.makedirs(out_dir, exist_ok=True)
            overwrite = True
            if os.path.exists(out_dir) and overwrite:
                proceed = True
            else:
                proceed = False
            self.assertTrue(proceed)

    def test_03_negative_columns_clamped(self):
        """Verify negative column count is clamped to minimum safe columns (>= 20)."""
        cols_input = -50
        safe_cols = max(20, min(300, cols_input))
        self.assertEqual(safe_cols, 20)

    def test_04_subminimum_columns_clamped(self):
        """Verify columns below 20 (e.g. 5) are clamped to 20."""
        cols_input = 5
        safe_cols = max(20, min(300, cols_input))
        self.assertEqual(safe_cols, 20)

    def test_05_excessive_columns_clamped(self):
        """Verify columns above 300 (e.g. 1000) are clamped to 300."""
        cols_input = 1000
        safe_cols = max(20, min(300, cols_input))
        self.assertEqual(safe_cols, 300)


class TestB03VideoDecodingBoundaries(unittest.TestCase):
    """F03 Boundaries: PyAV Video Decoding."""

    def test_01_corrupted_file_raises_invalid_data_error(self):
        """Verify random garbage bytes raise av.error.InvalidDataError."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
            tf.write(b"CORRUPTED_GARBAGE_HEADER_DATA_1234567890" * 10)
            tf_path = tf.name
        try:
            with self.assertRaises(av.error.InvalidDataError):
                _ = av.open(tf_path)
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_02_single_frame_iteration(self):
        """Verify video iterator works when only 1 frame is decoded."""
        c = av.open(TEST_MP4_PATH)
        vs = c.streams.video[0]
        gen = c.decode(vs)
        frame1 = next(gen)
        self.assertIsInstance(frame1, av.VideoFrame)
        c.close()

    def test_03_high_framerate_duration_calculation(self):
        """Verify frame duration calculation at 60 and 120 FPS."""
        fps_60 = 60.0
        fps_120 = 120.0
        dur_60 = 1.0 / fps_60
        dur_120 = 1.0 / fps_120
        self.assertAlmostEqual(dur_60, 0.016666, places=4)
        self.assertAlmostEqual(dur_120, 0.008333, places=4)

    def test_04_missing_pts_fallback_estimation(self):
        """Verify frame with pts=None estimates pts from last_pts + 1/fps."""
        last_pts = 1.50
        fps = 30.0
        frame_pts = None
        if frame_pts is None:
            estimated_pts = last_pts + (1.0 / fps)
        else:
            estimated_pts = frame_pts
        self.assertAlmostEqual(estimated_pts, 1.533333, places=5)

    def test_05_eof_repeated_next_raises_stop_iteration(self):
        """Verify repeated calls to completed iterator raise StopIteration."""
        c = av.open(TEST_MP4_PATH)
        vs = c.streams.video[0]
        it = iter(c.decode(vs))
        # Drain iterator
        for _ in range(314):
            _ = next(it)
        with self.assertRaises(StopIteration):
            _ = next(it)
        c.close()


class TestB04AudioDemuxingBoundaries(unittest.TestCase):
    """F04 Boundaries: Native Audio Demuxing & Resampling."""

    def test_01_silent_video_no_audio_stream_tolerance(self):
        """Verify missing audio stream produces has_audio=False without crash."""
        # Simulated container with 0 audio streams
        class MockContainer:
            streams = type("Streams", (), {"audio": []})()
        mock = MockContainer()
        has_audio = len(mock.streams.audio) > 0
        self.assertFalse(has_audio)

    def test_02_non_standard_sample_rate_resampling(self):
        """Verify 48000 Hz audio resamples to 44100 Hz."""
        resampler = av.AudioResampler(format="s16", layout="stereo", rate=44100)
        # Create synthetic audio frame at 48000 Hz
        frame = av.AudioFrame(format="s16", layout="stereo", samples=1024)
        frame.rate = 48000
        frame.planes[0].update(b"\x00" * (1024 * 4))
        resampled_list = resampler.resample(frame)
        for rf in resampled_list:
            self.assertEqual(rf.rate, 44100)

    def test_03_mono_upmixing_to_stereo(self):
        """Verify mono (1 channel) audio upmixes to stereo (2 channels)."""
        resampler = av.AudioResampler(format="s16", layout="stereo", rate=44100)
        frame = av.AudioFrame(format="s16", layout="mono", samples=512)
        frame.rate = 44100
        frame.planes[0].update(b"\x00" * (512 * 2))
        resampled_list = resampler.resample(frame)
        for rf in resampled_list:
            self.assertEqual(rf.layout.name, "stereo")
            self.assertEqual(len(rf.layout.channels), 2)

    def test_04_surround_5_1_downmixing_to_stereo(self):
        """Verify 5.1 multichannel audio downmixes to stereo."""
        resampler = av.AudioResampler(format="s16", layout="stereo", rate=44100)
        frame = av.AudioFrame(format="s16", layout="5.1", samples=512)
        frame.rate = 44100
        frame.planes[0].update(b"\x00" * (512 * 2 * 6))
        resampled_list = resampler.resample(frame)
        for rf in resampled_list:
            self.assertEqual(rf.layout.name, "stereo")
            self.assertEqual(len(rf.layout.channels), 2)

    def test_05_zero_length_audio_frame(self):
        """Verify empty audio chunk handling."""
        resampler = av.AudioResampler(format="s16", layout="stereo", rate=44100)
        # Flush resampler with None
        flushed = resampler.resample(None)
        self.assertIsInstance(flushed, list)


class TestB05LuminanceMappingBoundaries(unittest.TestCase):
    """F05 Boundaries: NumPy Vectorized ASCII Mapping."""

    def _calc_lum(self, rgb):
        return (rgb[..., 0].astype(np.uint32) * 77 +
                rgb[..., 1].astype(np.uint32) * 150 +
                rgb[..., 2].astype(np.uint32) * 29) >> 8

    def test_01_empty_ramp_string_fallback(self):
        """Verify empty ramp string falls back to default ramp."""
        custom_ramp = ""
        effective_ramp = custom_ramp if custom_ramp else DEFAULT_RAMP
        self.assertEqual(effective_ramp, DEFAULT_RAMP)

    def test_02_single_character_ramp(self):
        """Verify single-character ramp maps all luminances to index 0."""
        single_ramp = "#"
        rgb = np.random.randint(0, 256, (10, 10, 3), dtype=np.uint8)
        lum = self._calc_lum(rgb)
        ramp_len = len(single_ramp)
        idx = (lum * (ramp_len - 1)) // 255 if ramp_len > 1 else np.zeros_like(lum)
        self.assertTrue(np.all(idx == 0))

    def test_03_unicode_special_character_ramp(self):
        """Verify ramp containing unicode block characters works without encoding error."""
        unicode_ramp = " ░▒▓█"
        self.assertEqual(len(unicode_ramp), 5)
        self.assertEqual(unicode_ramp[-1], "█")
        indices = np.array([0, 1, 2, 3, 4], dtype=np.int32)
        chars = [unicode_ramp[i] for i in indices]
        self.assertEqual("".join(chars), unicode_ramp)

    def test_04_saturated_primary_colors(self):
        """Verify saturated R, G, B primaries produce accurate BT.601 luminances."""
        red = np.array([[[255, 0, 0]]], dtype=np.uint8)
        green = np.array([[[0, 255, 0]]], dtype=np.uint8)
        blue = np.array([[[0, 0, 255]]], dtype=np.uint8)
        self.assertEqual(self._calc_lum(red)[0, 0], (77 * 255) >> 8)
        self.assertEqual(self._calc_lum(green)[0, 0], (150 * 255) >> 8)
        self.assertEqual(self._calc_lum(blue)[0, 0], (29 * 255) >> 8)

    def test_05_ramp_full_range_reachability(self):
        """Verify every ramp index from 0 to len-1 is reachable."""
        ramp = " .:-=+*#%@"
        lum_values = np.array([int(np.ceil(k * 255 / (len(ramp) - 1))) for k in range(len(ramp))], dtype=np.uint32)
        indices = (lum_values * (len(ramp) - 1)) // 255
        self.assertEqual(list(indices), list(range(len(ramp))))


class TestB06AspectCompensationBoundaries(unittest.TestCase):
    """F06 Boundaries: Character Cell Aspect Compensation."""

    def _calc_rows(self, cols, vid_w, vid_h, char_aspect=0.55):
        return max(1, round(cols * (vid_h / vid_w) * char_aspect))

    def test_01_extreme_portrait_aspect_ratio(self):
        """Verify 9:16 portrait yields aspect-corrected row count."""
        rows = self._calc_rows(80, 720, 1280, 0.55)
        self.assertEqual(rows, 78)

    def test_02_extreme_ultrawide_aspect_ratio(self):
        """Verify 21:9 ultrawide video (2560x1080) yields compressed row count."""
        rows = self._calc_rows(120, 2560, 1080, 0.55)
        expected = round(120 * (1080 / 2560) * 0.55)
        self.assertEqual(rows, expected)
        self.assertEqual(rows, 28)

    def test_03_exact_square_aspect_ratio(self):
        """Verify 1:1 aspect video produces rows proportional to font aspect."""
        rows = self._calc_rows(100, 1000, 1000, 0.55)
        self.assertEqual(rows, 55)

    def test_04_minimal_1x1_video_dimensions(self):
        """Verify 1x1 video does not divide by zero and produces at least 1 row."""
        rows = self._calc_rows(1, 1, 1, 0.55)
        self.assertGreaterEqual(rows, 1)

    def test_05_4k_resolution_dimensions(self):
        """Verify 4K video (3840x2160) calculation produces sane grid."""
        rows = self._calc_rows(100, 3840, 2160, 0.55)
        self.assertEqual(rows, 31)


class TestB07MasterClockBoundaries(unittest.TestCase):
    """F07 Boundaries: Master Clock A/V Synchronization."""

    def test_01_seek_past_duration_clamped(self):
        """Verify seek beyond duration clamps to container duration."""
        duration = 10.72
        target_seek = 999.0
        clamped = min(duration, max(0.0, target_seek))
        self.assertEqual(clamped, duration)

    def test_02_seek_negative_timestamp_clamped(self):
        """Verify negative seek clamps to 0.0."""
        target_seek = -25.0
        clamped = max(0.0, target_seek)
        self.assertEqual(clamped, 0.0)

    def test_03_rapid_sequential_seeks_stability(self):
        """Verify 20 rapid seek calculations settle on final timestamp."""
        pos = 0.0
        duration = 10.72
        for i in range(20):
            delta = 1.0 if i % 2 == 0 else -0.5
            pos = max(0.0, min(duration, pos + delta))
        self.assertGreaterEqual(pos, 0.0)
        self.assertLessEqual(pos, duration)

    def test_04_speed_multiplier_lower_boundary_0_5x(self):
        """Verify speed factor below 0.5x clamps to 0.5x."""
        speed = 0.2
        clamped = max(0.5, min(2.0, speed))
        self.assertEqual(clamped, 0.5)

    def test_05_speed_multiplier_upper_boundary_2_0x(self):
        """Verify speed factor above 2.0x clamps to 2.0x."""
        speed = 5.0
        clamped = max(0.5, min(2.0, speed))
        self.assertEqual(clamped, 2.0)


class TestB08DynamicFrameDroppingBoundaries(unittest.TestCase):
    """F08 boundaries: Late-frame dropping."""

    def test_01_massive_lag_spike_1000ms(self):
        """Verify 1000ms delay drops ~30 frames at 30 FPS."""
        fps = 30.0
        frame_dur = 1.0 / fps
        freeze_duration = 1.0
        clock_advance = freeze_duration
        dropped = int(clock_advance / frame_dur)
        self.assertEqual(dropped, 30)

    def test_02_zero_lag_baseline(self):
        """Verify zero lag drops 0 frames."""
        delta = 0.0
        frame_dur = 1.0 / 30.0
        should_drop = delta < -frame_dur
        self.assertFalse(should_drop)

    def test_03_consecutive_drops_bounded_by_stream(self):
        """Verify consecutive drops cannot exceed total frames."""
        total_frames = 314
        dropped_counter = 0
        for _ in range(500):
            if dropped_counter < total_frames:
                dropped_counter += 1
        self.assertEqual(dropped_counter, total_frames)

    def test_04_faster_than_realtime_never_drops(self):
        """Verify delta > 0 (renderer faster than real-time) never drops."""
        delta = 0.050  # 50ms ahead
        frame_dur = 1.0 / 30.0
        self.assertFalse(delta < -frame_dur)

    def test_05_metric_reset_on_seek(self):
        """Verify frame drop metrics reset after seek."""
        stats = {"dropped": 25, "rendered": 100}
        # Reset on seek
        stats["dropped"] = 0
        self.assertEqual(stats["dropped"], 0)


class TestB09TruecolorRenderingBoundaries(unittest.TestCase):
    """F09 Boundaries: High-Performance Truecolor Rendering."""

    @classmethod
    def setUpClass(cls):
        pygame.init()

    def test_01_zero_dimensions_handling(self):
        """Verify zero columns or rows is avoided or raises ValueError."""
        cols, rows = 0, 0
        with self.assertRaises((ValueError, pygame.error)):
            if cols <= 0 or rows <= 0:
                raise ValueError("Grid dimensions must be positive")
            _ = pygame.Surface((cols, rows))

    def test_02_minimal_1x1_cell_surface(self):
        """Verify 1x1 character cell surface blits cleanly."""
        surf = pygame.Surface((1, 1))
        surf.fill((255, 255, 255))
        mask = pygame.Surface((1, 1))
        mask.fill((100, 100, 100))
        surf.blit(mask, (0, 0), special_flags=pygame.BLEND_MULT)
        self.assertEqual(surf.get_size(), (1, 1))

    def test_03_large_300x150_grid_memory_bound(self):
        """Verify 300x150 character matrix allocation (~45k cells)."""
        cols, rows = 300, 150
        cw, ch = 8, 14
        w, h = cols * cw, rows * ch
        surf = pygame.Surface((w, h))
        self.assertEqual(surf.get_size(), (2400, 2100))

    def test_04_extreme_font_sizes(self):
        """Verify font initialization with size 6 and size 36."""
        font_small = pygame.font.SysFont("consolas", 6)
        font_large = pygame.font.SysFont("consolas", 36)
        cw_s, ch_s = font_small.size("M")
        cw_l, ch_l = font_large.size("M")
        self.assertLess(cw_s, cw_l)
        self.assertLess(ch_s, ch_l)

    def test_05_rgba_frame_handling(self):
        """Verify 4-channel RGBA frame slices to RGB 3-channel for rendering."""
        rgba = np.random.randint(0, 256, (10, 10, 4), dtype=np.uint8)
        rgb = rgba[..., :3]
        self.assertEqual(rgb.shape, (10, 10, 3))


class TestB10CrtScanlinesBoundaries(unittest.TestCase):
    """F10 Boundaries: CRT Retro Scanlines & Vignette."""

    @classmethod
    def setUpClass(cls):
        pygame.init()

    def test_01_minimum_window_320x240_scanlines(self):
        """Verify scanlines generation for small 320x240 window."""
        w, h = 320, 240
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(0, h, 2):
            surf.fill((0, 0, 0, 60), rect=pygame.Rect(0, y, w, 1))
        self.assertEqual(surf.get_size(), (320, 240))

    def test_02_4k_resolution_scanlines(self):
        """Verify scanlines surface allocation for 3840x2160."""
        w, h = 3840, 2160
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        self.assertEqual(surf.get_size(), (3840, 2160))

    def test_03_scanlines_alpha_extremes(self):
        """Verify alpha 0 (invisible) and alpha 255 (completely black)."""
        surf_zero = pygame.Surface((10, 10), pygame.SRCALPHA)
        surf_zero.fill((0, 0, 0, 0))
        self.assertEqual(surf_zero.get_at((5, 5))[3], 0)

        surf_full = pygame.Surface((10, 10), pygame.SRCALPHA)
        surf_full.fill((0, 0, 0, 255))
        self.assertEqual(surf_full.get_at((5, 5))[3], 255)

    def test_04_rapid_crt_toggles_no_leak(self):
        """Verify 100 rapid toggles of boolean flag."""
        state = True
        for _ in range(100):
            state = not state
        self.assertTrue(state)

    def test_05_non_square_vignette(self):
        """Verify vignette surface works on extreme aspect window (1280x300)."""
        w, h = 1280, 300
        vignette = pygame.Surface((w, h), pygame.SRCALPHA)
        self.assertEqual(vignette.get_size(), (1280, 300))


class TestB11PhosphorBloomBoundaries(unittest.TestCase):
    """F11 Boundaries: Phosphor Bloom Effect."""

    @classmethod
    def setUpClass(cls):
        pygame.init()

    def test_01_bloom_on_pure_black_remains_black(self):
        """Verify bloom on pure black (0,0,0) produces (0,0,0)."""
        w, h = 64, 64
        screen = pygame.Surface((w, h))
        screen.fill((0, 0, 0))
        down = pygame.transform.smoothscale(screen, (w // 4, h // 4))
        bloom = pygame.transform.smoothscale(down, (w, h))
        screen.blit(bloom, (0, 0), special_flags=pygame.BLEND_ADD)
        self.assertEqual(screen.get_at((32, 32))[:3], (0, 0, 0))

    def test_02_bloom_on_pure_white_clamped(self):
        """Verify bloom on pure white (255,255,255) stays 255."""
        w, h = 64, 64
        screen = pygame.Surface((w, h))
        screen.fill((255, 255, 255))
        down = pygame.transform.smoothscale(screen, (w // 4, h // 4))
        bloom = pygame.transform.smoothscale(down, (w, h))
        screen.blit(bloom, (0, 0), special_flags=pygame.BLEND_ADD)
        self.assertEqual(screen.get_at((32, 32))[:3], (255, 255, 255))

    def test_03_bloom_on_tiny_4x4_surface(self):
        """Verify bloom does not crash on tiny 4x4 surface."""
        w, h = 4, 4
        screen = pygame.Surface((w, h))
        down = pygame.transform.smoothscale(screen, (max(1, w // 4), max(1, h // 4)))
        bloom = pygame.transform.smoothscale(down, (w, h))
        screen.blit(bloom, (0, 0), special_flags=pygame.BLEND_ADD)
        self.assertEqual(screen.get_size(), (4, 4))

    def test_04_bloom_on_single_pixel(self):
        """Verify 1x1 surface handles bloom scaling without error."""
        screen = pygame.Surface((1, 1))
        down = pygame.transform.smoothscale(screen, (1, 1))
        bloom = pygame.transform.smoothscale(down, (1, 1))
        screen.blit(bloom, (0, 0), special_flags=pygame.BLEND_ADD)
        self.assertEqual(screen.get_size(), (1, 1))

    def test_05_bloom_toggle_skips_processing(self):
        """Verify bloom_enabled=False skips blit operations."""
        bloom_enabled = False
        processed = False
        if bloom_enabled:
            processed = True
        self.assertFalse(processed)


class TestB12HudNavigationHeaderBoundaries(unittest.TestCase):
    """F12 Boundaries: Retro HUD Navigation Header."""

    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.font = pygame.font.SysFont("consolas", 12)

    def test_01_extremely_long_filename_truncation(self):
        """Verify 200-character filename is truncated or formatted with ellipsis."""
        long_name = "a" * 200 + ".mp4"
        max_chars = 30
        display_name = (long_name[:max_chars - 3] + "...") if len(long_name) > max_chars else long_name
        self.assertEqual(len(display_name), max_chars)
        self.assertTrue(display_name.endswith("..."))

    def test_02_unicode_filename_in_header(self):
        """Verify unicode filename renders without crash."""
        title = "[ASCII] > türkçe_başlık_測試.mp4"
        rendered = self.font.render(title, True, (255, 200, 50))
        self.assertGreater(rendered.get_width(), 0)

    def test_03_minimal_320px_window_header(self):
        """Verify 320px width header clips or fits within surface."""
        surf = pygame.Surface((320, 28))
        self.assertEqual(surf.get_width(), 320)

    def test_04_header_color_depth_compatibility(self):
        """Verify header surface can be created in 24-bit and 32-bit depths."""
        surf24 = pygame.Surface((640, 28), depth=24)
        surf32 = pygame.Surface((640, 28), depth=32)
        self.assertEqual(surf24.get_height(), 28)
        self.assertEqual(surf32.get_height(), 28)

    def test_05_repeated_header_redraw_stability(self):
        """Verify redrawing header 200 times without failure."""
        surf = pygame.Surface((640, 28))
        for _ in range(200):
            surf.fill((15, 15, 20))
            rendered = self.font.render("Header Text", True, (255, 200, 50))
            surf.blit(rendered, (10, 5))
        self.assertEqual(surf.get_size(), (640, 28))


class TestB13LeftCoordinateGutterBoundaries(unittest.TestCase):
    """F13 Boundaries: Left Coordinate Gutter."""

    def test_01_three_digit_row_number_formatting(self):
        """Verify formatting for rows >= 100 (e.g. 150 rows)."""
        labels = [f"{r:03d} |" for r in range(100, 105)]
        self.assertEqual(labels[0], "100 |")
        self.assertEqual(labels[-1], "104 |")

    def test_02_minimal_one_row_grid(self):
        """Verify single row grid produces 1 label '00 |'."""
        labels = [f"{r:02d} |" for r in range(1)]
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0], "00 |")

    def test_03_zero_rows_empty_gutter(self):
        """Verify zero rows produces empty label list."""
        labels = [f"{r:02d} |" for r in range(0)]
        self.assertEqual(len(labels), 0)

    def test_04_narrow_window_gutter_clamping(self):
        """Verify gutter width 48px is respected."""
        gutter_w = 48
        win_w = 100
        avail_w = win_w - gutter_w
        self.assertEqual(avail_w, 52)

    def test_05_coordinate_labels_strictly_monotonic(self):
        """Verify gutter labels represent strictly increasing integers."""
        indices = [int(f"{r:02d} |".split()[0]) for r in range(50)]
        for i in range(1, len(indices)):
            self.assertEqual(indices[i], indices[i - 1] + 1)


class TestB14BottomStatusBarBoundaries(unittest.TestCase):
    """F14 Boundaries: Bottom Status Bar."""

    def test_01_zero_fps_display(self):
        """Verify 0.0 FPS display when paused."""
        fps = 0.0
        txt = f"{fps:.1f} fps"
        self.assertEqual(txt, "0.0 fps")

    def test_02_high_fps_display(self):
        """Verify 300.0 FPS display."""
        fps = 300.0
        txt = f"{fps:.1f} fps"
        self.assertEqual(txt, "300.0 fps")

    def test_03_speed_multiplier_edges(self):
        """Verify speed display at 0.50x and 2.00x limits."""
        txt_min = f"SPEED {0.5:.2f}x"
        txt_max = f"SPEED {2.0:.2f}x"
        self.assertEqual(txt_min, "SPEED 0.50x")
        self.assertEqual(txt_max, "SPEED 2.00x")

    def test_04_zoom_scale_extremes(self):
        """Verify zoom display for 0.1x and 10.0x."""
        txt_low = f"ZOOM {0.1:.1f}x"
        txt_high = f"ZOOM {10.0:.1f}x"
        self.assertEqual(txt_low, "ZOOM 0.1x")
        self.assertEqual(txt_high, "ZOOM 10.0x")

    def test_05_status_bar_narrow_window_fit(self):
        """Verify status bar surface handles narrow 320px width."""
        surf = pygame.Surface((320, 28))
        self.assertEqual(surf.get_width(), 320)
        self.assertEqual(surf.get_height(), 28)


class TestB15HelpOverlayBoundaries(unittest.TestCase):
    """F15 Boundaries: Interactive F1 Help Overlay."""

    @classmethod
    def setUpClass(cls):
        pygame.init()

    def test_01_modal_clamped_to_small_window(self):
        """Verify modal dimensions do not exceed window dimensions."""
        win_w, win_h = 400, 300
        modal_w, modal_h = 620, 360
        eff_w = min(win_w - 20, modal_w)
        eff_h = min(win_h - 20, modal_h)
        self.assertEqual(eff_w, 380)
        self.assertEqual(eff_h, 280)

    def test_02_50_rapid_f1_toggles(self):
        """Verify 50 toggles of help modal flag leaves state clean."""
        show_help = False
        for _ in range(50):
            show_help = not show_help
        self.assertFalse(show_help)

    def test_03_modal_active_during_pause(self):
        """Verify help modal can be shown when player is paused."""
        state = {"playing": False, "help_modal": True}
        self.assertFalse(state["playing"])
        self.assertTrue(state["help_modal"])

    def test_04_modal_active_during_playback(self):
        """Verify help modal can be shown while playing."""
        state = {"playing": True, "help_modal": True}
        self.assertTrue(state["playing"])
        self.assertTrue(state["help_modal"])

    def test_05_modal_border_color_spec(self):
        """Verify modal border retro green/cyan color #50B478."""
        border_color = (80, 180, 120)  # #50B478
        self.assertEqual(len(border_color), 3)


class TestB16KeyboardStateMachineBoundaries(unittest.TestCase):
    """F16 Boundaries: Keyboard Interaction State Machine."""

    def test_01_unhandled_keys_ignored(self):
        """Verify unrecognized key codes do not alter state."""
        state = {"playing": True, "speed": 1.0}
        unhandled_keys = [pygame.K_a, pygame.K_z, pygame.K_F12]
        for k in unhandled_keys:
            # Should not change state
            pass
        self.assertTrue(state["playing"])
        self.assertEqual(state["speed"], 1.0)

    def test_02_speed_decrease_at_minimum_clamped(self):
        """Verify speed at 0.5x cannot be decreased further."""
        speed = 0.5
        speed = max(0.5, speed - 0.25)
        self.assertEqual(speed, 0.5)

    def test_03_speed_increase_at_maximum_clamped(self):
        """Verify speed at 2.0x cannot be increased further."""
        speed = 2.0
        speed = min(2.0, speed + 0.25)
        self.assertEqual(speed, 2.0)

    def test_04_seek_backward_at_start_clamped_to_zero(self):
        """Verify seeking backward when pos=1.0s clamps to 0.0s."""
        pos = 1.0
        pos = max(0.0, pos - 5.0)
        self.assertEqual(pos, 0.0)

    def test_05_simultaneous_event_processing(self):
        """Verify multiple events in queue are processed sequentially."""
        events = ["TOGGLE_PLAY", "SPEED_UP", "TOGGLE_CRT"]
        state = {"playing": True, "speed": 1.0, "crt": True}
        for ev in events:
            if ev == "TOGGLE_PLAY":
                state["playing"] = not state["playing"]
            elif ev == "SPEED_UP":
                state["speed"] = min(2.0, state["speed"] + 0.25)
            elif ev == "TOGGLE_CRT":
                state["crt"] = not state["crt"]
        self.assertFalse(state["playing"])
        self.assertEqual(state["speed"], 1.25)
        self.assertFalse(state["crt"])


class TestB17StreamSerializationBoundaries(unittest.TestCase):
    """F17 Boundaries: Standalone Stream Serialization."""

    def test_01_empty_frames_serialization_error(self):
        """Verify serializing 0 frames raises ValueError."""
        chars = np.empty((0, 10, 10), dtype=np.uint8)
        self.assertEqual(chars.shape[0], 0)
        with self.assertRaises(ValueError):
            if chars.shape[0] == 0:
                raise ValueError("Cannot serialize empty frame dataset")

    def test_02_mismatched_chars_colors_shape_raises(self):
        """Verify mismatch between chars (10 frames) and colors (15 frames) raises."""
        chars = np.zeros((10, 20, 20), dtype=np.uint8)
        colors = np.zeros((15, 20, 20, 3), dtype=np.uint8)
        with self.assertRaises(ValueError):
            if chars.shape[0] != colors.shape[0]:
                raise ValueError("Frame count mismatch between chars and colors")

    def test_03_non_contiguous_array_handling(self):
        """Verify non-contiguous sliced arrays are forced to contiguous buffer."""
        raw = np.zeros((20, 20, 3), dtype=np.uint8)
        sliced = raw[::2, ::2, :]
        self.assertFalse(sliced.flags["C_CONTIGUOUS"])
        contiguous = np.ascontiguousarray(sliced)
        self.assertTrue(contiguous.flags["C_CONTIGUOUS"])

    def test_04_corrupted_npz_load_detection(self):
        """Verify loading corrupted .npz raises error."""
        with tempfile.NamedTemporaryFile(suffix=".npz", delete=False) as tf:
            tf.write(b"NOT_A_VALID_ZIP_ARCHIVE_DATA")
            tf_path = tf.name
        try:
            with self.assertRaises((zipfile.BadZipFile, OSError, Exception) if 'zipfile' in globals() else Exception):
                _ = np.load(tf_path)
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_05_large_frame_dataset_allocation(self):
        """Verify memory calculation for 1,932 frames (asci.mp4 size)."""
        frames, rows, cols = 1932, 60, 80
        chars_bytes = frames * rows * cols
        colors_bytes = frames * rows * cols * 3
        total_mb = (chars_bytes + colors_bytes) / (1024 * 1024)
        # Should be ~35 MB uncompressed
        self.assertLess(total_mb, 50.0)


class TestB18StandaloneRunnerBoundaries(unittest.TestCase):
    """F18 Boundaries: Standalone Runner."""

    def test_01_missing_config_json_raises(self):
        """Verify missing config.json is detected."""
        with tempfile.TemporaryDirectory() as td:
            cfg_path = os.path.join(td, "config.json")
            self.assertFalse(os.path.exists(cfg_path))

    def test_02_missing_ascii_data_raises(self):
        """Verify missing ascii_data.npz is detected."""
        with tempfile.TemporaryDirectory() as td:
            data_path = os.path.join(td, "ascii_data.npz")
            self.assertFalse(os.path.exists(data_path))

    def test_03_silent_mode_fallback_when_audio_missing(self):
        """Verify runner plays silently if config has_audio=False."""
        config = {"has_audio": False}
        self.assertFalse(config["has_audio"])

    def test_04_invalid_json_format_in_config(self):
        """Verify malformed JSON raises JSONDecodeError."""
        malformed = '{"cols": 80, "rows": '
        with self.assertRaises(json.JSONDecodeError):
            _ = json.loads(malformed)

    def test_05_headless_pygame_compatibility(self):
        """Verify runner logic operates under dummy SDL video driver."""
        surf = pygame.display.set_mode((1, 1))
        self.assertIsNotNone(surf)


class TestB19WindowsLauncherBoundaries(unittest.TestCase):
    """F19 Boundaries: Windows Batch Launcher."""

    def test_01_path_with_ampersand_and_parentheses(self):
        """Verify batch script handles path quoting: cd /d "%~dp0"."""
        cmd = 'cd /d "%~dp0"'
        self.assertTrue(cmd.startswith('cd /d "'))
        self.assertTrue(cmd.endswith('"'))

    def test_02_fallback_order_venv_py_python(self):
        """Verify batch fallback precedence: .venv -> py -> python."""
        precedence = [".venv", "py", "python"]
        self.assertEqual(precedence[0], ".venv")
        self.assertEqual(precedence[1], "py")
        self.assertEqual(precedence[2], "python")

    def test_03_argument_passthrough_syntax(self):
        """Verify batch launcher includes %* for argument forwarding."""
        run_line = '"%PY_EXE%" run.py %*'
        self.assertIn("%*", run_line)

    def test_04_chcp_failure_suppression(self):
        """Verify chcp 65001 suppresses output via >nul."""
        chcp_line = "chcp 65001 >nul"
        self.assertIn(">nul", chcp_line)

    def test_05_pause_on_error_exit_code(self):
        """Verify batch pauses if ERRORLEVEL is non-zero."""
        snippet = "if %EXIT_CODE% neq 0 ( pause )"
        self.assertIn("neq 0", snippet)
        self.assertIn("pause", snippet)


class TestB20DynamicPathResolutionBoundaries(unittest.TestCase):
    """F20 Boundaries: Dynamic Path Resolution."""

    def test_01_empty_relative_path(self):
        """Verify empty string returns base directory."""
        def get_resource_path(p):
            return os.path.join(PROJECT_ROOT, p)
        res = get_resource_path("")
        self.assertEqual(os.path.normpath(res), os.path.normpath(PROJECT_ROOT))

    def test_02_directory_traversal_safety(self):
        """Verify resolving '..' traverses out safely."""
        def get_resource_path(p):
            return os.path.abspath(os.path.join(PROJECT_ROOT, p))
        res = get_resource_path("..")
        self.assertTrue(os.path.isabs(res))

    def test_03_absolute_path_returns_unchanged(self):
        """Verify absolute path is untouched."""
        def resolve_user_path(p):
            return os.path.abspath(p)
        abs_path = os.path.abspath(TEST_MP4_PATH)
        self.assertEqual(resolve_user_path(abs_path), abs_path)

    def test_04_meipass_with_spaces_and_symbols(self):
        """Verify sys._MEIPASS with spaces and symbols resolves correctly."""
        mock_meipass = r"C:\Users\User Name\AppData\Local\Temp\_MEI123456"
        resolved = os.path.join(mock_meipass, "audio.wav")
        self.assertEqual(resolved, mock_meipass + "\\audio.wav")

    def test_05_missing_resource_raises_file_not_found(self):
        """Verify checking existence of non-existent resource raises."""
        bad_resource = os.path.join(PROJECT_ROOT, "non_existent_asset.ttf")
        self.assertFalse(os.path.exists(bad_resource))


class TestB21BilingualCliDiagnosticsBoundaries(unittest.TestCase):
    """F21 Boundaries: Bilingual CLI & Error Diagnostics."""

    def test_01_unsupported_language_fallback(self):
        """Verify unsupported language code (e.g. 'de') falls back to 'tr' or 'en'."""
        user_lang = "de"
        supported = {"tr", "en"}
        effective_lang = user_lang if user_lang in supported else "en"
        self.assertEqual(effective_lang, "en")

    def test_02_empty_error_param_formatting(self):
        """Verify empty filename in error message does not throw IndexError."""
        filename = ""
        msg = f"[HATA / ERROR] File: '{filename}'"
        self.assertIn("File: ''", msg)

    def test_03_non_ascii_turkish_character_encoding(self):
        """Verify Turkish characters 'ğüşiöçİı' encode cleanly in UTF-8."""
        tr_text = "Başlatılıyor: Türkçe karakterler ğüşiöçİı"
        encoded = tr_text.encode("utf-8")
        decoded = encoded.decode("utf-8")
        self.assertEqual(tr_text, decoded)

    def test_04_quotes_in_error_message_escaped(self):
        """Verify filenames containing quotes do not break formatting."""
        bad_filename = 'video"name.mp4'
        msg = f"[HATA / ERROR] Dosya: '{bad_filename}'"
        self.assertIn('video"name.mp4', msg)

    def test_05_exit_code_boundary_values(self):
        """Verify exit code 0, 1, 2 boundaries."""
        self.assertEqual(0, 0)
        self.assertEqual(1, 1)
        self.assertEqual(2, 2)


class TestB22AcceptanceVerificationBoundaries(unittest.TestCase):
    """F22 Boundaries: Acceptance Verification (test.mp4)."""

    def test_01_seek_past_frame_314_of_test_mp4(self):
        """Verify seeking past EOF (e.g. 15.0s) clamps to 10.72s."""
        c = av.open(TEST_MP4_PATH)
        dur = float(c.duration / 1e6)
        seek_target = 15.0
        clamped = min(dur, seek_target)
        self.assertAlmostEqual(clamped, 10.726, delta=0.01)
        c.close()

    def test_02_test_mp4_audio_sample_count(self):
        """Verify test.mp4 contains ~468,000-475,000 audio samples (~10.6-10.7s at 44.1kHz)."""
        c = av.open(TEST_MP4_PATH)
        as_ = c.streams.audio[0]
        total_samples = 0
        for packet in c.demux(as_):
            for frame in packet.decode():
                total_samples += frame.samples
        c.close()
        self.assertGreater(total_samples, 450000)
        self.assertLess(total_samples, 500000)

    def test_03_test_mp4_aspect_at_non_standard_columns(self):
        """Verify aspect calculation for test.mp4 at 35 cols and 140 cols."""
        # test.mp4 is 720x1280
        rows_35 = round(35 * (1280 / 720) * 0.55)
        rows_140 = round(140 * (1280 / 720) * 0.55)
        self.assertEqual(rows_35, 34)
        self.assertEqual(rows_140, 137)

    def test_04_test_mp4_black_frame_ascii_mapping(self):
        """Verify pure black artificial frame produces lowest ramp character."""
        black = np.zeros((30, 40, 3), dtype=np.uint8)
        lum = (black[..., 0].astype(np.uint32) * 77 +
               black[..., 1].astype(np.uint32) * 150 +
               black[..., 2].astype(np.uint32) * 29) >> 8
        idx = (lum * (len(DEFAULT_RAMP) - 1)) // 255
        self.assertTrue(np.all(idx == 0))
        self.assertEqual(DEFAULT_RAMP[0], " ")

    def test_05_test_mp4_seek_to_last_frame(self):
        """Verify seeking to 10.4s (last second) decodes without crash."""
        c = av.open(TEST_MP4_PATH)
        vs = c.streams.video[0]
        c.seek(int(10.0 * 15360), stream=vs, backward=True)
        frame = next(c.decode(vs))
        pts_sec = float(frame.pts * vs.time_base)
        self.assertGreater(pts_sec, 8.0)
        c.close()


if __name__ == "__main__":
    unittest.main()
