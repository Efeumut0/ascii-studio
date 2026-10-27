import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from ascii_ui.hud import HudRenderer
from standalone_template.run import StandaloneHudRenderer


class TestGraphiteHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.font.init()

    def test_live_and_exported_player_share_graphite_help(self):
        from unittest.mock import patch

        from standalone_template.help_overlay import draw_help_overlay

        screen = pygame.Surface((900, 600))
        for renderer, standalone in ((HudRenderer(), False), (StandaloneHudRenderer(), True)):
            renderer.language = "tr"
            renderer.seek_step = 30
            with patch("standalone_template.help_overlay.draw_help_overlay", wraps=draw_help_overlay) as draw:
                if standalone:
                    renderer.draw_help_modal(screen, seek_step=30)
                else:
                    renderer.draw_help_modal(screen)
                self.assertEqual(draw.call_args.kwargs["language"], "tr")
                self.assertEqual(draw.call_args.kwargs["seek_step"], 30)
                self.assertEqual(draw.call_args.kwargs["standalone"], standalone)

    def test_help_lists_actual_controls_and_current_seek_step(self):
        from standalone_template.help_overlay import shortcut_rows

        live = dict(shortcut_rows("tr", 12.5, standalone=False))
        exported = dict(shortcut_rows("en", 30, standalone=True))
        self.assertIn("12,5 sn", live["← / →"])
        self.assertIn("30 s", exported["← / →"])
        self.assertIn("Tab", live)
        self.assertNotIn("Tab", exported)
        self.assertNotIn("F / F11", live)
        self.assertIn("F / F11", exported)

    def test_help_stays_inside_small_and_portrait_windows(self):
        from standalone_template.help_overlay import draw_help_overlay

        for size in ((900, 600), (400, 300), (360, 640), (240, 180)):
            screen = pygame.Surface(size)
            screen.fill((80, 80, 80))
            bounds = draw_help_overlay(screen, language="tr", seek_step=5, standalone=True)
            self.assertTrue(screen.get_rect().contains(bounds))
            self.assertEqual(bounds.center, screen.get_rect().center)
            self.assertTrue(all(abs(actual - expected) <= 3 for actual, expected in
                                zip(screen.get_at(bounds.center)[:3], (36, 38, 40))))
            self.assertLess(screen.get_at((0, 0))[0], 80)


if __name__ == "__main__":
    unittest.main()
