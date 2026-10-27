"""Tests for render resolution, window configuration, and icons."""

from __future__ import annotations

import json
import os
import unittest

import numpy as np
import pygame

# Headless drivers
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import ascii_gui
import ascii_video_renderer
from ascii_ui.renderer import AsciiRenderer


class TestTier7ResolutionAndWindowed(unittest.TestCase):
    """Tier 7 test suite for render resolution, windowed player mode, and taskbar icon."""

    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.font.init()

    def test_01_resolution_auto_low_resolution_targets_1080p(self):
        """Auto resolution on low-resolution grids (e.g. 80 cols x 25 rows) must scale up to 1080p."""
        tw, th, fs = ascii_video_renderer.resolve_render_resolution(
            resolution="auto",
            cols=80,
            rows=25,
            base_font_size=12,
            duration=30.0,
            video_aspect=16 / 9,
        )
        self.assertEqual(tw, 1920)
        self.assertEqual(th, 1080)
        self.assertGreater(fs, 12, "Optimal font size for 1080p must be significantly larger than base 12")

    def test_02_resolution_auto_high_resolution_short_video_targets_2k(self):
        """Auto resolution on already-high-res grid for short video (<= 180s) must upgrade to 2K (1440p)."""
        tw, th, fs = ascii_video_renderer.resolve_render_resolution(
            resolution="auto",
            cols=300,
            rows=100,
            base_font_size=12,
            duration=60.0,
            video_aspect=16 / 9,
        )
        self.assertEqual(tw, 2560)
        self.assertEqual(th, 1440)
        self.assertGreater(fs, 2)

    def test_03_resolution_auto_high_resolution_long_video_optimizes_1080p(self):
        """Auto resolution on long video (> 180s) optimizes for speed by targeting 1080p instead of 2K."""
        tw, th, _ = ascii_video_renderer.resolve_render_resolution(
            resolution="auto",
            cols=300,
            rows=100,
            base_font_size=12,
            duration=360.0,
            video_aspect=16 / 9,
        )
        self.assertEqual(tw, 1920)
        self.assertEqual(th, 1080)

    def test_04_resolution_explicit_tiers(self):
        """Explicit resolution selections (720p, 1080p, 2K, 4K, original) must produce exact dimensions."""
        # 720p
        tw, th, _ = ascii_video_renderer.resolve_render_resolution(
            resolution="720p", cols=80, rows=25, base_font_size=12, duration=10.0, video_aspect=16 / 9
        )
        self.assertEqual(tw, 1280)
        self.assertEqual(th, 720)

        # 1080p
        tw, th, _ = ascii_video_renderer.resolve_render_resolution(
            resolution="1080p", cols=80, rows=25, base_font_size=12, duration=10.0, video_aspect=16 / 9
        )
        self.assertEqual(tw, 1920)
        self.assertEqual(th, 1080)

        # 2K
        tw, th, _ = ascii_video_renderer.resolve_render_resolution(
            resolution="2k", cols=80, rows=25, base_font_size=12, duration=10.0, video_aspect=16 / 9
        )
        self.assertEqual(tw, 2560)
        self.assertEqual(th, 1440)

        # Original / native
        tw, th, fs = ascii_video_renderer.resolve_render_resolution(
            resolution="original", cols=80, rows=25, base_font_size=12, duration=10.0, video_aspect=16 / 9
        )
        self.assertIsNone(tw)
        self.assertIsNone(th)
        self.assertEqual(fs, 12)

    def test_05_resolution_aspect_ratio_portrait(self):
        """Vertical/portrait video (9:16) must correctly invert canvas to portrait (e.g. 1080x1920 for 1080p)."""
        tw, th, _ = ascii_video_renderer.resolve_render_resolution(
            resolution="1080p", cols=50, rows=90, base_font_size=12, duration=15.0, video_aspect=9 / 16
        )
        self.assertEqual(tw, 1080)
        self.assertEqual(th, 1920)

    def test_06_resolution_custom_dimensions(self):
        """Custom WxH strings (e.g. '1280x720', '800x600') must be parsed into even dimensions."""
        tw, th, _ = ascii_video_renderer.resolve_render_resolution(
            resolution="1280x720", cols=80, rows=25, base_font_size=12, duration=10.0
        )
        self.assertEqual(tw, 1280)
        self.assertEqual(th, 720)

    def test_07_render_to_rgb_array_centering(self):
        """render_to_rgb_array with target_shape must center the ASCII grid and preserve true vector curves."""
        r = AsciiRenderer(font_size=30)
        cw, ch = r.get_cell_size()
        cols, rows = 40, 20
        chars = np.full((rows, cols), 5, dtype=np.int32)
        colors = np.full((rows, cols, 3), 200, dtype=np.uint8)

        target_h, target_w = 800, 1200
        canvas = r.render_to_rgb_array(chars, colors, color_mode="truecolor", target_shape=(target_h, target_w))
        self.assertEqual(canvas.shape, (800, 1200, 3))

        # Check that margins around centered frame are black (0, 0, 0)
        grid_w = cols * cw
        grid_h = rows * ch
        off_x = (target_w - grid_w) // 2
        off_y = (target_h - grid_h) // 2

        if off_y > 2:
            self.assertEqual(np.sum(canvas[0, :, :]), 0, "Top margin must be pure black")
        if off_x > 2:
            self.assertEqual(np.sum(canvas[:, 0, :]), 0, "Left margin must be pure black")

    def test_08_gui_default_size_calibrated_to_screenshot(self):
        """AsciiStudioGui default window size must match calibrated client dimensions: 1024 x 740."""
        gui = ascii_gui.AsciiStudioGui()
        self.assertEqual(gui.width, 1024)
        self.assertEqual(gui.height, 740)

    def test_09_gui_cycle_render_resolution(self):
        """GUI cycle_render_resolution method cycles through all 6 resolution options (including 4K)."""
        gui = ascii_gui.AsciiStudioGui(width=1024, height=740)
        self.assertEqual(gui.selected_resolution_idx, 0)
        self.assertEqual(gui.render_resolutions[gui.selected_resolution_idx]["id"], "auto")

        # Cycle once: 1080p
        gui.cycle_render_resolution()
        self.assertEqual(gui.render_resolutions[gui.selected_resolution_idx]["id"], "1080p")
        self.assertIn("1080p", gui.status_message)

        # Cycle twice: 2k
        gui.cycle_render_resolution()
        self.assertEqual(gui.render_resolutions[gui.selected_resolution_idx]["id"], "2k")

        # Cycle 3 times: 4k
        gui.cycle_render_resolution()
        self.assertEqual(gui.render_resolutions[gui.selected_resolution_idx]["id"], "4k")
        self.assertIn("4K", gui.status_message)

        # Cycle 4 times: 720p
        gui.cycle_render_resolution()
        self.assertEqual(gui.render_resolutions[gui.selected_resolution_idx]["id"], "720p")

        # Cycle 5 times: original
        gui.cycle_render_resolution()
        self.assertEqual(gui.render_resolutions[gui.selected_resolution_idx]["id"], "original")

        # Cycle 6 times: back to auto
        gui.cycle_render_resolution()
        self.assertEqual(gui.render_resolutions[gui.selected_resolution_idx]["id"], "auto")

    def test_10_gui_resolution_card_and_button_interaction(self):
        """TOGGLE_RESOLUTION button is rendered and clickable in settings panel."""
        gui = ascii_gui.AsciiStudioGui(width=1024, height=740)
        gui.draw()
        self.assertIn("TOGGLE_RESOLUTION", gui.rendered_buttons)
        res_rect = gui.rendered_buttons["TOGGLE_RESOLUTION"]
        self.assertGreater(res_rect.width, 100)
        self.assertGreater(res_rect.height, 20)

        # Simulate click
        init_idx = gui.selected_resolution_idx
        gui.handle_click(res_rect.center)
        self.assertEqual(gui.selected_resolution_idx, (init_idx + 1) % len(gui.render_resolutions))

    def test_11_standalone_player_fullscreen_default_false(self):
        """Standalone player template and output/test/config.json must have fullscreen_default: False."""
        # Check output/test/config.json
        test_cfg_path = os.path.join("output", "test", "config.json")
        if os.path.exists(test_cfg_path):
            with open(test_cfg_path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertFalse(data.get("fullscreen_default", True), "fullscreen_default must be False for windowed start")

        # Check standalone_template/run.py content
        template_run = os.path.join("standalone_template", "run.py")
        with open(template_run, encoding="utf-8") as f:
            content = f.read()
        self.assertIn('cfg.get("fullscreen_default", False)', content)

    def test_12_taskbar_and_window_icon_setup(self):
        """Icon files must exist and SetCurrentProcessExplicitAppUserModelID logic must be present."""
        icon_png = os.path.join("assets", "eye_icon.png")
        self.assertTrue(os.path.exists(icon_png), "assets/eye_icon.png must exist")

        gui_path = "ascii_gui.py"
        with open(gui_path, encoding="utf-8") as f:
            gui_code = f.read()
        self.assertIn("SetCurrentProcessExplicitAppUserModelID", gui_code)
        self.assertIn("set_icon", gui_code)
        self.assertIn("apply_windows_app_icon", gui_code)

    def test_13_player_state_and_hud_renderer_clean_mode(self):
        """PlayerState.show_hud defaults to False, suppressing edge chrome while preserving F1 help modal."""
        import ascii_player
        from ascii_ui.hud import HudRenderer, PlayerState

        state = PlayerState(filename="test.mp4")
        self.assertFalse(state.show_hud, "show_hud must default to False for clean windowed playback")

        # When show_hud is False, draw_hud should not modify the background of header/gutter/status
        hud_inst = HudRenderer()
        canvas = pygame.Surface((800, 600))
        canvas.fill((0, 0, 0))
        hud_inst.draw_hud(canvas, state, total_rows=50, char_height=12)

        # Confirm surface is still pure black (0 chrome drawn)
        arr = pygame.surfarray.array3d(canvas)
        self.assertEqual(np.sum(arr), 0, "Canvas must remain pure black when show_hud is False")

        # When show_help is True, help modal is rendered
        state.show_help = True
        hud_inst.draw_hud(canvas, state, total_rows=50, char_height=12)
        arr_modal = pygame.surfarray.array3d(canvas)
        self.assertGreater(np.sum(arr_modal), 0, "Help modal overlay must render when show_help is True")

        # Verify ascii_player parser defaults --hud to False
        parser = ascii_player.create_parser()
        args = parser.parse_args(["-i", "test.mp4"])
        self.assertFalse(args.hud, "--hud must default to False")

    def test_14_input_handler_escape_modal_dismiss(self):
        """ESC key closes help modal overlay first instead of quitting immediately."""
        from ascii_ui.hud import PlayerState
        from ascii_ui.input_handler import InputHandler

        handler = InputHandler()
        state = PlayerState(status="PLAYING", show_help=True)
        action = handler.handle_key(pygame.K_ESCAPE, state)
        self.assertEqual(action, "CLOSE_HELP")
        self.assertFalse(state.show_help)
        self.assertFalse(handler.should_quit)
        self.assertEqual(state.status, "PLAYING")

        # Next ESC key terminates player
        action2 = handler.handle_key(pygame.K_ESCAPE, state)
        self.assertEqual(action2, "QUIT")
        self.assertTrue(handler.should_quit)
        self.assertEqual(state.status, "STOPPED")

    def test_15_apply_windows_app_icon_present_across_modules(self):
        """All main executables must define and call apply_windows_app_icon."""
        for path in ("ascii_gui.py", "ascii_player.py", os.path.join("standalone_template", "run.py")):
            with open(path, encoding="utf-8") as f:
                code = f.read()
            self.assertIn("def apply_windows_app_icon", code, f"{path} must define apply_windows_app_icon")
            self.assertIn("apply_windows_app_icon(self.screen)" if "ascii_gui.py" in path else "apply_windows_app_icon(screen)", code)

    def test_16_4k_resolution_renderer(self):
        """Renderer resolves 4k target resolution to 3840x2160 with valid font size."""
        tw, th, fs = ascii_video_renderer.resolve_render_resolution(
            "4k", cols=80, rows=45, base_font_size=12, duration=10.0, video_aspect=16 / 9
        )
        self.assertEqual(tw, 3840)
        self.assertEqual(th, 2160)
        self.assertGreaterEqual(fs, 20)

    def test_17_console_hiding_defined_in_executables(self):
        """Console window hiding snippet is present in ascii_gui.py, ascii_player.py, and standalone_template/run.py."""
        for path in ("ascii_gui.py", "ascii_player.py", os.path.join("standalone_template", "run.py")):
            with open(path, encoding="utf-8") as f:
                code = f.read()
            self.assertIn("GetConsoleWindow", code, f"{path} must contain GetConsoleWindow")
            self.assertIn("ShowWindow", code, f"{path} must contain ShowWindow")

    def test_18_gui_right_click_reverse_cycling_and_toggles(self):
        """Right-clicking (button=3) reverse-cycles resolutions, colors, seek steps, and toggles settings."""
        gui = ascii_gui.AsciiStudioGui(width=1024, height=740)
        gui.draw()

        # Resolution toggle button
        res_rect = gui.rendered_buttons["TOGGLE_RESOLUTION"]
        # Left click: 0 (auto) -> 1 (1080p)
        gui.handle_click(res_rect.center, button=1)
        self.assertEqual(gui.selected_resolution_idx, 1)

        # Right click: 1 (1080p) -> 0 (auto)
        gui.handle_click(res_rect.center, button=3)
        self.assertEqual(gui.selected_resolution_idx, 0)

        # Right click from 0 -> last (original)
        gui.handle_click(res_rect.center, button=3)
        self.assertEqual(gui.selected_resolution_idx, len(gui.render_resolutions) - 1)

        # Color toggle button
        color_rect = gui.rendered_buttons["TOGGLE_COLOR"]
        gui.selected_color_theme_idx = 0
        gui.handle_click(color_rect.center, button=3)
        self.assertEqual(gui.selected_color_theme_idx, len(gui.color_themes) - 1)

        # Seek toggle button
        seek_rect = gui.rendered_buttons["TOGGLE_SEEK"]
        gui.seek_step_idx = 0
        gui.handle_click(seek_rect.center, button=3)
        self.assertEqual(gui.seek_step_idx, len(gui.SEEK_STEPS) - 1)

        # CRT toggle with right click
        crt_rect = gui.rendered_buttons["TOGGLE_CRT"]
        init_crt = gui.crt_enabled
        gui.handle_click(crt_rect.center, button=3)
        self.assertEqual(gui.crt_enabled, not init_crt)

        # Quality header button right-click reverse cycling
        self.assertIn("HEADER_QUALITY", gui.rendered_buttons)
        q_head_rect = gui.rendered_buttons["HEADER_QUALITY"]
        gui.selected_quality_idx = 2
        gui.handle_click(q_head_rect.center, button=3)
        self.assertEqual(gui.selected_quality_idx, 1)

        # Quality active preset right-click reverse cycling
        active_card = gui.rendered_quality_rects[1][1]
        gui.handle_click(active_card.center, button=3)
        self.assertEqual(gui.selected_quality_idx, 0)

        # Video selection with right-click must NOT initiate dragging
        if gui.rendered_video_rects:
            v_rect = gui.rendered_video_rects[0][1]
            gui.handle_click(v_rect.center, button=3)
            self.assertEqual(gui.dragging_video_idx, -1)
            gui.handle_mouse_move((v_rect.centerx + 20, v_rect.centery + 20))
            self.assertFalse(gui.is_dragging_video, "Right-click on video must never initiate drag-and-drop")

    def test_19_font_init_resilience_in_compute_font_size(self):
        """compute_optimal_render_font_size and resolve_render_resolution must initialize fonts if not already init."""
        fs = ascii_video_renderer.compute_optimal_render_font_size(1920, 1080, 80, 45)
        self.assertGreaterEqual(fs, 10)
        tw, th, opt_fs = ascii_video_renderer.resolve_render_resolution(
            "4k", cols=100, rows=50, base_font_size=12, duration=10.0, video_aspect=16 / 9
        )
        self.assertEqual(tw, 3840)
        self.assertEqual(th, 2160)
        self.assertGreaterEqual(opt_fs, 20)

    def test_20_ascii_exporter_create_no_window(self):
        """ascii_exporter.py must use CREATE_NO_WINDOW when invoking PyInstaller on Windows."""
        with open("ascii_exporter.py", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("CREATE_NO_WINDOW", code)
        self.assertIn("popen_kwargs", code)


if __name__ == "__main__":
    unittest.main()
