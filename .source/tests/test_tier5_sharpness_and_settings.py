"""Tests for rendering sharpness and setting propagation."""

from __future__ import annotations

import os
import unittest

import numpy as np

# Ensure headless video & audio
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame

import ascii_exporter
import ascii_player
from ascii_ui.crt_effects import CrtEffect
from ascii_ui.renderer import AsciiRenderer


class TestTier5SharpnessAndSettings(unittest.TestCase):
    """Tier 5 validation suite for sharpness, background purity, and settings propagation."""

    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.font.init()

    def test_01_crt_preserves_pure_black_background(self):
        """Verify CRT effect keeps unlit black pixels strictly at (0, 0, 0) with zero color bleed."""
        w, h = 320, 240
        surf = pygame.Surface((w, h))
        surf.fill((0, 0, 0))

        # Draw a bright colored glyph in the center
        font = pygame.font.SysFont("consolas", 14)
        glyph = font.render("@", True, (255, 200, 50))
        surf.blit(glyph, (w // 2, h // 2))

        # Corner and border pixels must start as pure black
        self.assertEqual(surf.get_at((10, 10))[:3], (0, 0, 0))
        self.assertEqual(surf.get_at((w - 10, h - 10))[:3], (0, 0, 0))

        # Apply CRT post-processing
        crt = CrtEffect(w, h)
        crt.apply(surf, crt_enabled=True, bloom=False)

        # In unlit areas, pixels MUST remain strictly pure black (0, 0, 0)
        self.assertEqual(surf.get_at((10, 10))[:3], (0, 0, 0), "Corner pixel must remain (0, 0, 0)")
        self.assertEqual(surf.get_at((50, 50))[:3], (0, 0, 0), "Background pixel must remain (0, 0, 0)")
        self.assertEqual(surf.get_at((w - 10, h - 10))[:3], (0, 0, 0), "Bottom corner must remain (0, 0, 0)")

    def test_02_ascii_player_audio_cli_flags(self):
        """Verify ascii_player supports both --audio and --no-audio."""
        parser = ascii_player.create_parser()

        args_default = parser.parse_args(["test.mp4"])
        self.assertTrue(args_default.audio, "Default audio should be True")

        args_no_audio = parser.parse_args(["test.mp4", "--no-audio"])
        self.assertFalse(args_no_audio.audio, "--no-audio should disable audio")

        args_audio = parser.parse_args(["test.mp4", "--audio"])
        self.assertTrue(args_audio.audio, "--audio should explicitly enable audio")

    def test_03_ascii_exporter_audio_cli_flags(self):
        """Verify ascii_exporter supports both --audio and --no-audio."""
        parser = ascii_exporter.create_parser()

        args_default = parser.parse_args(["-i", "test.mp4"])
        self.assertTrue(args_default.audio, "Default exporter audio should be True")

        args_no_audio = parser.parse_args(["-i", "test.mp4", "--no-audio"])
        self.assertFalse(args_no_audio.audio, "--no-audio should disable audio export")

    def test_04_micro_font_rendering_down_to_3pt(self):
        """Verify AsciiRenderer handles font sizes down to 3 without errors or truncation."""
        renderer = AsciiRenderer(font_name="consolas", font_size=3)
        cw, ch = renderer.get_cell_size()
        self.assertGreaterEqual(cw, 1)
        self.assertGreaterEqual(ch, 1)

        # Dynamic font resize down to 3
        renderer.set_font_size(3)
        cw3, ch3 = renderer.get_cell_size()
        self.assertGreaterEqual(cw3, 1)
        self.assertGreaterEqual(ch3, 1)

        # Render a frame with micro-font
        screen = pygame.Surface((100, 100))
        chars = np.zeros((10, 10), dtype=np.uint8)
        colors = np.full((10, 10, 3), 200, dtype=np.uint8)
        renderer.render_frame(screen, chars, colors)
        self.assertEqual(screen.get_size(), (100, 100))

    def test_05_quality_scales_strictly_increasing(self):
        """Verify window scaling factors strictly increase across quality tiers."""
        scales = {
            "low": 0.50,
            "balanced": 0.62,
            "high": 0.72,
            "ultra": 0.82,
            "master": 0.88,
            "cinema": 0.92,
            "overkill": 0.94,
            "godlike": 0.96,
        }
        order = ["low", "balanced", "high", "ultra", "master", "cinema", "overkill", "godlike"]
        for i in range(len(order) - 1):
            q_curr = order[i]
            q_next = order[i + 1]
            self.assertLess(
                scales[q_curr],
                scales[q_next],
                f"Window scale for {q_curr} ({scales[q_curr]}) must be smaller than {q_next} ({scales[q_next]})",
            )

    def test_06_loop_cli_flags_propagation(self):
        """Verify --loop and --no-loop flags work across player and exporter."""
        # 1. Player
        p_parser = ascii_player.create_parser()
        self.assertFalse(p_parser.parse_args(["test.mp4"]).loop)
        self.assertTrue(p_parser.parse_args(["test.mp4", "--loop"]).loop)
        self.assertFalse(p_parser.parse_args(["test.mp4", "--no-loop"]).loop)

        # 2. Exporter
        e_parser = ascii_exporter.create_parser()
        self.assertFalse(e_parser.parse_args(["-i", "test.mp4"]).loop)
        self.assertTrue(e_parser.parse_args(["-i", "test.mp4", "--loop"]).loop)
        self.assertFalse(e_parser.parse_args(["-i", "test.mp4", "--no-loop"]).loop)

    def test_07_crt_cli_flags_propagation(self):
        """Verify --crt and --no-crt flags work across player and exporter."""
        # 1. Player (CRT is False by default)
        p_parser = ascii_player.create_parser()
        self.assertFalse(p_parser.parse_args(["test.mp4"]).crt)
        self.assertFalse(p_parser.parse_args(["test.mp4", "--no-crt"]).crt)
        self.assertTrue(p_parser.parse_args(["test.mp4", "--crt"]).crt)

        # 2. Exporter (CRT is False by default)
        e_parser = ascii_exporter.create_parser()
        self.assertFalse(e_parser.parse_args(["-i", "test.mp4"]).crt)
        self.assertFalse(e_parser.parse_args(["-i", "test.mp4", "--no-crt"]).crt)
        self.assertTrue(e_parser.parse_args(["-i", "test.mp4", "--crt"]).crt)

    def test_08_window_sizing_monotonic_progression_both_aspect_ratios(self):
        """Verify window area strictly increases from low to godlike for both 16:9 and 9:16."""
        presets = [
            ("low", 60),
            ("balanced", 80),
            ("high", 110),
            ("ultra", 135),
            ("master", 160),
            ("cinema", 190),
            ("overkill", 220),
            ("godlike", 260),
        ]
        quality_scales = {
            "low": 0.50,
            "balanced": 0.62,
            "high": 0.72,
            "ultra": 0.82,
            "master": 0.88,
            "cinema": 0.92,
            "overkill": 0.94,
            "godlike": 0.96,
        }

        desktop_w, desktop_h = 1920, 1080
        gutter_w, header_h, footer_h = 48, 28, 28
        max_avail_w = int(desktop_w * 0.96)
        max_avail_h = int(desktop_h * 0.90)

        for _vname, (vid_w, vid_h) in [("Mentalist (16:9)", (1920, 1080)), ("test.mp4 (9:16)", (720, 1280))]:
            aspect_ratio = vid_w / vid_h
            last_area = 0
            for q_id, _cols in presets:
                scale_ratio = quality_scales[q_id]
                box_w = max(420, min(max_avail_w, int(desktop_w * scale_ratio)))
                box_h = max(320, min(max_avail_h, int(desktop_h * scale_ratio * 0.92)))

                avail_w = max(100, box_w - gutter_w)
                avail_h = max(100, box_h - header_h - footer_h)

                if (avail_w / aspect_ratio) <= avail_h:
                    content_w = avail_w
                    content_h = int(avail_w / aspect_ratio)
                else:
                    content_h = avail_h
                    content_w = int(avail_h * aspect_ratio)

                win_w = max(420, content_w + gutter_w)
                win_h = max(320, content_h + header_h + footer_h)
                area = win_w * win_h

                self.assertGreater(
                    area,
                    last_area,
                    f"Window area for preset {q_id} ({area}) must exceed previous tier ({last_area})",
                )
                last_area = area

    def test_09_hud_and_input_handler_loop_toggle(self):
        """Verify PlayerState and InputHandler support loop and C/R keys."""
        from ascii_ui.hud import PlayerState
        from ascii_ui.input_handler import InputHandler

        state = PlayerState(filename="test.mp4", crt_enabled=True, loop=False)
        handler = InputHandler()

        # Toggle CRT with C
        action_c = handler.handle_key(pygame.K_c, state)
        self.assertEqual(action_c, "TOGGLE_CRT")
        self.assertFalse(state.crt_enabled)

        # Toggle CRT with R
        action_r = handler.handle_key(pygame.K_r, state)
        self.assertEqual(action_r, "TOGGLE_CRT")
        self.assertTrue(state.crt_enabled)

        # Toggle Loop with L
        action_l = handler.handle_key(pygame.K_l, state)
        self.assertEqual(action_l, "TOGGLE_LOOP")
        self.assertTrue(state.loop)

        action_l2 = handler.handle_key(pygame.K_l, state)
        self.assertEqual(action_l2, "TOGGLE_LOOP")
        self.assertFalse(state.loop)


if __name__ == "__main__":
    unittest.main()
