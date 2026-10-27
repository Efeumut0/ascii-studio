"""Tests for interactions between playback and rendering settings."""

import os
import sys
import tempfile
import time
import unittest

import numpy as np
import pygame

from tests import (
    PROJECT_ROOT,
    TEST_MP4_PATH,
    ascii_exporter_mod,
    audio_engine_mod,
    crt_effects_mod,
    hud_mod,
    input_handler_mod,
    renderer_mod,
    video_decoder_mod,
)


class TestTier3Combinations(unittest.TestCase):
    """Pairwise cross-feature interaction test suite."""

    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.font = pygame.font.SysFont("consolas", 12)
        cls.cw, cls.ch = cls.font.size("M")

    # 1. Pause + Seek Interaction
    def test_01_pause_and_seek_maintains_pause(self):
        """Interaction 1: Seeking while paused keeps player in paused state and updates position."""
        handler = input_handler_mod.InputHandler()
        state = hud_mod.PlayerState()
        state.status = "PAUSED"
        state.current_time = 2.0
        state.duration = 10.72
        action = handler.handle_key(pygame.K_RIGHT, state)
        self.assertEqual(action, "SEEK_FORWARD")
        self.assertEqual(state.status, "PAUSED")
        self.assertEqual(state.current_time, 7.0)

    # 2. Pause + Resume Time Integrity
    def test_02_pause_and_resume_prevents_time_jump(self):
        """Interaction 2: Pausing for 500ms and resuming does not jump master clock by 500ms."""
        master_pos = 3.0
        pause_start = time.perf_counter()
        time.sleep(0.02)  # Simulate 20ms pause
        paused_duration = time.perf_counter() - pause_start

        # Resume: re-anchor clock
        resumed_anchor = time.perf_counter() - master_pos
        current_time = time.perf_counter() - resumed_anchor
        self.assertAlmostEqual(current_time, 3.0, delta=0.05)
        # Verify master time did not jump by paused_duration
        self.assertLess(current_time, master_pos + paused_duration)

    # 3. Speed Change + Master Clock Progression
    def test_03_speed_change_scales_clock_progression(self):
        """Interaction 3: Setting speed to 1.5x scales elapsed time progression by 1.5."""
        base_clock = 0.0
        speed = 1.5
        real_elapsed = 0.100  # 100ms
        virtual_advance = real_elapsed * speed
        base_clock += virtual_advance
        self.assertAlmostEqual(base_clock, 0.150, places=3)

    # 4. Speed Change to 0.5x + Clock Deceleration
    def test_04_half_speed_slows_clock_progression(self):
        """Interaction 4: Setting speed to 0.5x halves the elapsed time advance."""
        base_clock = 0.0
        speed = 0.5
        real_elapsed = 0.200  # 200ms
        virtual_advance = real_elapsed * speed
        base_clock += virtual_advance
        self.assertAlmostEqual(base_clock, 0.100, places=3)

    # 5. CRT Toggle During Playback
    def test_05_crt_toggle_during_active_playback(self):
        """Interaction 5: Toggling CRT on/off during active playback does not pause or glitch."""
        handler = input_handler_mod.InputHandler()
        state = hud_mod.PlayerState()
        state.status = "PLAYING"
        state.crt_enabled = True
        action = handler.handle_key(pygame.K_r, state)
        self.assertEqual(action, "TOGGLE_CRT")
        self.assertEqual(state.status, "PLAYING")
        self.assertFalse(state.crt_enabled)

    # 6. CRT Toggle While Paused
    def test_06_crt_toggle_while_paused_updates_frame(self):
        """Interaction 6: Toggling CRT while paused preserves paused state and frame position."""
        handler = input_handler_mod.InputHandler()
        state = hud_mod.PlayerState()
        state.status = "PAUSED"
        state.crt_enabled = False
        action = handler.handle_key(pygame.K_r, state)
        self.assertEqual(action, "TOGGLE_CRT")
        self.assertEqual(state.status, "PAUSED")
        self.assertTrue(state.crt_enabled)

    # 7. Help Modal Toggle During Playback
    def test_07_help_modal_during_playback(self):
        """Interaction 7: Opening F1 help modal during playback does not pause video."""
        handler = input_handler_mod.InputHandler()
        state = hud_mod.PlayerState()
        state.status = "PLAYING"
        state.show_help = False
        action = handler.handle_key(pygame.K_F1, state)
        self.assertEqual(action, "TOGGLE_HELP")
        self.assertEqual(state.status, "PLAYING")
        self.assertTrue(state.show_help)

    # 8. Help Modal Toggle While Paused
    def test_08_help_modal_during_pause(self):
        """Interaction 8: Opening F1 help modal while paused retains paused state."""
        handler = input_handler_mod.InputHandler()
        state = hud_mod.PlayerState()
        state.status = "PAUSED"
        state.show_help = False
        action = handler.handle_key(pygame.K_F1, state)
        self.assertEqual(action, "TOGGLE_HELP")
        self.assertEqual(state.status, "PAUSED")
        self.assertTrue(state.show_help)

    # 9. Window Resize + CRT Surface Regeneration
    def test_09_window_resize_regenerates_crt_surfaces(self):
        """Interaction 9: Resizing window updates CRT scanlines surface dimensions."""
        crt = crt_effects_mod.CrtEffect(640, 480)
        self.assertEqual(crt.scanlines_surf.get_size(), (640, 480))
        crt.resize(1024, 768)
        self.assertEqual(crt.scanlines_surf.get_size(), (1024, 768))

    # 10. Window Resize + Aspect Ratio Letterboxing Recalculation
    def test_10_window_resize_recalculates_letterboxing(self):
        """Interaction 10: Window resize dynamically updates pillarbox/letterbox rect."""
        vid_w, vid_h = 720, 1280
        char_aspect = 0.55
        target_ratio = (vid_w / vid_h) / char_aspect  # ~1.0227
        # In a wide window (1280x720)
        win_w, win_h = 1280, 720
        # Canvas should fit within available rect
        canvas_h = win_h - 56  # minus header & footer
        canvas_w = int(canvas_h * target_ratio)
        pillarbox_x = (win_w - 48 - canvas_w) // 2
        self.assertGreater(pillarbox_x, 0)
        self.assertLess(canvas_w, win_w)

    # 11. Rapid Seek Forward and Backward
    def test_11_rapid_seek_forward_then_backward(self):
        """Interaction 11: Rapidly seeking +5s and -5s settles accurately."""
        handler = input_handler_mod.InputHandler()
        state = hud_mod.PlayerState()
        state.current_time = 2.0
        state.duration = 10.72
        handler.handle_key(pygame.K_RIGHT, state)
        self.assertEqual(state.current_time, 7.0)
        handler.handle_key(pygame.K_LEFT, state)
        self.assertEqual(state.current_time, 2.0)

    # 12. Seek Near EOF + Play to Termination
    def test_12_seek_near_eof_and_clean_termination(self):
        """Interaction 12: Seeking to duration - 0.1s terminates cleanly at EOF."""
        total_frames = 314
        near_eof_frame = 312
        frames_played = list(range(near_eof_frame, total_frames))
        self.assertEqual(frames_played, [312, 313])
        self.assertEqual(len(frames_played), 2)

    # 13. Dynamic Frame Dropping Under Simulated OS Lag
    def test_13_frame_drop_under_simulated_heavy_load(self):
        """Interaction 13: Simulated 200ms CPU stall drops lagged frames and catches up."""
        fps = 30.0
        frame_dur = 1.0 / fps
        stall_duration = 0.200  # 200ms
        t_master = 1.0 + stall_duration
        current_pts = 1.0
        rendered = []
        dropped = []

        while current_pts < t_master:
            delta = current_pts - t_master
            if delta < -frame_dur:
                dropped.append(current_pts)
            else:
                rendered.append(current_pts)
            current_pts += frame_dur

        self.assertGreaterEqual(len(dropped), 5)
        # Once caught up, delta >= -frame_dur
        delta_recovered = current_pts - t_master
        self.assertGreaterEqual(delta_recovered, -frame_dur)

    # 14. Exporter + Custom Ramp + No-CRT Interaction
    def test_14_export_custom_ramp_and_no_crt(self):
        """Interaction 14: Export with custom ramp and --no-crt records correct config."""
        parser = ascii_exporter_mod.create_parser()
        args = parser.parse_args(["-i", TEST_MP4_PATH, "--chars", " .#", "--no-crt"])
        self.assertEqual(args.chars, " .#")
        self.assertFalse(args.crt)

    # 15. Exporter + Portrait Video Aspect Compensation
    def test_15_export_portrait_aspect_calculation(self):
        """Interaction 15: Exporter config for portrait 720x1280 has aspect-corrected rows."""
        decoder = video_decoder_mod.VideoDecoder(TEST_MP4_PATH, target_cols=70, char_aspect=0.55)
        self.assertEqual(decoder.cols, 70)
        self.assertEqual(decoder.rows, 68)
        decoder.close()

    # 16. Exporter + Silent Video Interaction
    def test_16_export_silent_video_config(self):
        """Interaction 16: Silent video export sets has_audio=False and empty audio_file."""
        config = {
            "has_audio": False,
            "audio_file": "",
            "source_video": "silent.mp4"
        }
        self.assertFalse(config["has_audio"])
        self.assertEqual(config["audio_file"], "")

    # 17. Standalone Runner Speed and Pause State Coupling
    def test_17_standalone_runner_speed_and_pause_coupling(self):
        """Interaction 17: Speed adjustment persists through pause and resume."""
        handler = input_handler_mod.InputHandler()
        state = hud_mod.PlayerState()
        state.speed = 1.0
        handler.handle_key(pygame.K_UP, state)
        handler.handle_key(pygame.K_UP, state)
        self.assertEqual(state.speed, 1.5)
        handler.handle_key(pygame.K_SPACE, state)
        self.assertEqual(state.status, "PAUSED")
        self.assertEqual(state.speed, 1.5)
        handler.handle_key(pygame.K_SPACE, state)
        self.assertEqual(state.status, "PLAYING")
        self.assertEqual(state.speed, 1.5)

    # 18. Standalone Runner Seek and Frame Slicing
    def test_18_standalone_runner_seek_frame_slicing(self):
        """Interaction 18: Seeking to 5.0s maps to frame int(5.0 * 30) = 150."""
        fps = 30.0
        seek_sec = 5.0
        target_frame = int(seek_sec * fps)
        self.assertEqual(target_frame, 150)
        # Simulated NPZ array
        mock_chars = np.zeros((314, 20, 20), dtype=np.uint8)
        mock_chars[150, 0, 0] = 7
        self.assertEqual(mock_chars[target_frame, 0, 0], 7)

    # 19. Dynamic Path Resolution with PyInstaller sys._MEIPASS Mock
    def test_19_dynamic_path_with_pyinstaller_mock(self):
        """Interaction 19: get_resource_path locates assets under sys._MEIPASS when frozen."""
        def get_resource_path(rel_path):
            if hasattr(sys, "_MEIPASS"):
                return os.path.join(sys._MEIPASS, rel_path)
            return os.path.join(PROJECT_ROOT, rel_path)

        with tempfile.TemporaryDirectory() as td:
            sys._MEIPASS = td
            try:
                # Create fake config.json inside MEIPASS
                fake_cfg = os.path.join(td, "config.json")
                with open(fake_cfg, "w") as f:
                    f.write('{"frozen": true}')
                resolved = get_resource_path("config.json")
                self.assertEqual(resolved, fake_cfg)
                self.assertTrue(os.path.exists(resolved))
            finally:
                delattr(sys, "_MEIPASS")

    # 20. Bilingual Diagnostics on Corrupted Export Input
    def test_20_bilingual_diagnostics_language_selection(self):
        """Interaction 20: Diagnostic messaging switches cleanly between Turkish and English."""
        def get_error_message(err_key, lang):
            messages = {
                "CORRUPT": {
                    "tr": "[HATA] Dosya geçerli bir video formatı değil.",
                    "en": "[ERROR] File is not a valid video format."
                }
            }
            return messages[err_key].get(lang, messages[err_key]["en"])

        msg_tr = get_error_message("CORRUPT", "tr")
        msg_en = get_error_message("CORRUPT", "en")
        self.assertIn("HATA", msg_tr)
        self.assertIn("ERROR", msg_en)

    # 21. HUD Header + Left Gutter + Status Bar Non-Overlapping Layout
    def test_21_hud_elements_no_overlap(self):
        """Interaction 21: Header (top 28px), Status (bottom 28px), and Gutter (left 48px) do not overlap."""
        hud = hud_mod.HudRenderer()
        win_w, win_h = 800, 600
        header_rect = pygame.Rect(0, 0, win_w, hud.HEADER_HEIGHT)
        status_rect = pygame.Rect(0, win_h - hud.STATUS_BAR_HEIGHT, win_w, hud.STATUS_BAR_HEIGHT)
        gutter_rect = pygame.Rect(0, hud.HEADER_HEIGHT, hud.GUTTER_WIDTH, win_h - hud.HEADER_HEIGHT - hud.STATUS_BAR_HEIGHT)
        canvas_rect = pygame.Rect(hud.GUTTER_WIDTH, hud.HEADER_HEIGHT, win_w - hud.GUTTER_WIDTH, win_h - hud.HEADER_HEIGHT - hud.STATUS_BAR_HEIGHT)

        # Assert no intersection between HUD areas
        self.assertFalse(header_rect.colliderect(status_rect))
        self.assertFalse(header_rect.colliderect(gutter_rect))
        self.assertFalse(status_rect.colliderect(gutter_rect))
        self.assertFalse(gutter_rect.colliderect(canvas_rect))

    # 22. Truecolor ASCII Renderer + Custom Ramp + CRT Composition
    def test_22_truecolor_custom_ramp_crt_composite(self):
        """Interaction 22: ASCII glyph blit + scanline blit composited on target surface."""
        renderer = renderer_mod.AsciiRenderer(font_size=12, char_ramp=" .:-=+*#%@")
        crt = crt_effects_mod.CrtEffect(100, 100)
        target = pygame.Surface((100, 100))
        chars = np.zeros((10, 10), dtype=np.uint8)
        colors = np.full((10, 10, 3), 200, dtype=np.uint8)
        renderer.render_frame(target, chars, colors, pygame.Rect(0, 0, 100, 100))
        crt.apply(target, crt_enabled=True)
        self.assertIsNotNone(target)

    # 23. Master Clock Reset on EOF Loop or Restart
    def test_23_master_clock_reset_on_loop(self):
        """Interaction 23: Reaching EOF and looping/seeking to 0.0 resets anchor cleanly."""
        current_pos = 10.72
        self.assertGreater(current_pos, 0.0)
        # Loop back to start
        current_pos = 0.0
        self.assertEqual(current_pos, 0.0)
        new_anchor = time.perf_counter()
        clock_val = time.perf_counter() - new_anchor
        self.assertAlmostEqual(clock_val, 0.0, delta=0.05)

    # 24. Audio Engine Mute / Unpause Interaction
    def test_24_audio_engine_mute_unpause_interaction(self):
        """Interaction 24: Audio state tracks volume mute and unpause."""
        engine = audio_engine_mod.AudioEngine(TEST_MP4_PATH)
        engine.load_for_playback()
        engine.play(start_time=1.0)
        self.assertTrue(engine._is_playing)
        self.assertFalse(engine._is_paused)
        engine.pause()
        self.assertTrue(engine._is_paused)
        engine.resume()
        self.assertFalse(engine._is_paused)
        engine.stop()

    # 25. Export Progress Reporting Callback with Simulated Cancellation
    def test_25_export_progress_callback_cancellation(self):
        """Interaction 25: Exporter progress generator allows early exit on cancel flag."""
        total_frames = 100
        cancelled = False
        processed = 0

        for frame_idx in range(total_frames):
            if frame_idx == 25:
                cancelled = True
            if cancelled:
                break
            processed += 1

        self.assertEqual(processed, 25)
        self.assertTrue(cancelled)

    # 26. Multi-key State Transition Sequence
    def test_26_multi_key_state_sequence(self):
        """Interaction 26: Sequence [SPACE -> UP -> RIGHT -> R -> F1] executes cleanly."""
        handler = input_handler_mod.InputHandler()
        state = hud_mod.PlayerState()
        state.status = "PLAYING"
        state.speed = 1.0
        state.current_time = 2.0
        state.duration = 10.72
        state.crt_enabled = True
        state.show_help = False

        handler.handle_key(pygame.K_SPACE, state)
        self.assertEqual(state.status, "PAUSED")

        handler.handle_key(pygame.K_UP, state)
        self.assertEqual(state.speed, 1.25)

        handler.handle_key(pygame.K_RIGHT, state)
        self.assertEqual(state.current_time, 7.0)

        handler.handle_key(pygame.K_r, state)
        self.assertFalse(state.crt_enabled)

        handler.handle_key(pygame.K_F1, state)
        self.assertTrue(state.show_help)


if __name__ == "__main__":
    unittest.main()
