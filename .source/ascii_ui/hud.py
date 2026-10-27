"""Playback header, row numbers, status bar, and keyboard help."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygame

from standalone_template import help_overlay

if TYPE_CHECKING:
    from pygame import Surface


@dataclass
class PlayerState:
    """Dataclass holding real-time video player UI state."""

    filename: str = ""
    status: str = "PLAYING"  # PLAYING, PAUSED, STOPPED
    fps: float = 0.0
    speed: float = 1.0
    zoom: float = 1.0
    current_time: float = 0.0
    duration: float = 0.0
    crt_enabled: bool = False
    loop: bool = False
    show_help: bool = False
    show_hud: bool = False  # Default False: clean windowed playback without edge borders
    has_audio: bool = True
    audio_enabled: bool = True
    color_mode: str = "truecolor"


class HudRenderer:
    """
    Renders retro-styled HUD chrome and interactive overlay modals.

    Layout conformance with asci.mp4:
    - Header height: 28px (#0F0F14, amber highlight #FFC832, border #323746)
    - Gutter width: 48px (#0C0C10, steel gray labels #505F6E, border #323746)
    - Status bar height: 28px (#0F0F14, phosphor green #64E682, amber #FFC832)
    - Help modal: Graphite keyboard guide shared with the exported player.
    """

    HEADER_HEIGHT = 28
    GUTTER_WIDTH = 48
    STATUS_BAR_HEIGHT = 28

    # Color Palette conforming to survey_explorer_2 & asci.mp4
    COLOR_HEADER_BG = (15, 15, 20)  # #0F0F14
    COLOR_GUTTER_BG = (12, 12, 16)  # #0C0C10
    COLOR_STATUS_BG = (15, 15, 20)  # #0F0F14
    COLOR_BORDER = (50, 55, 70)  # #323746
    COLOR_AMBER = (255, 200, 50)  # #FFC832
    COLOR_STEEL = (80, 95, 110)  # #505F6E
    COLOR_MUTED = (160, 165, 180)  # #A0A5B4
    COLOR_GREEN = (100, 230, 130)  # #64E682
    COLOR_WHITE = (235, 238, 245)
    COLOR_MODAL_BG = (16, 20, 28)  # #10141C
    COLOR_MODAL_BORDER = (80, 180, 120)  # #50B478

    def __init__(self, font_name: str = "consolas", font_size: int = 14) -> None:
        """
        Initialize HUD renderer with typography fonts.

        Args:
            font_name: System font name or TTF path.
            font_size: Standard base font size.
        """
        if not pygame.font.get_init():
            pygame.font.init()

        self.font_name = font_name
        self.font_size = font_size

        self.font = self._resolve_font(font_name, font_size)
        self.small_font = self._resolve_font(font_name, max(9, font_size - 2))
        self.modal_font = self._resolve_font(font_name, font_size)
        self.title_font = self._resolve_font(font_name, font_size + 2)

    def _resolve_font(self, font_name: str, font_size: int) -> pygame.font.Font:
        """Resolve a monospace font by path, system name, or fallback."""
        if os.path.isfile(font_name):
            try:
                return pygame.font.Font(font_name, font_size)
            except (pygame.error, OSError):
                pass

        matched = pygame.font.match_font(font_name)
        if matched and os.path.isfile(matched):
            try:
                return pygame.font.Font(matched, font_size)
            except (pygame.error, OSError):
                pass

        try:
            return pygame.font.SysFont(font_name, font_size)
        except (pygame.error, OSError):
            pass

        return pygame.font.Font(None, font_size)

    def draw_header(self, screen: Surface, state: PlayerState) -> None:
        """Draw top breadcrumb navigation header bar."""
        sw = screen.get_width()
        header_rect = pygame.Rect(0, 0, sw, self.HEADER_HEIGHT)
        pygame.draw.rect(screen, self.COLOR_HEADER_BG, header_rect)
        pygame.draw.line(
            screen,
            self.COLOR_BORDER,
            (0, self.HEADER_HEIGHT - 1),
            (sw, self.HEADER_HEIGHT - 1),
        )

        # File name display (truncate cleanly if too long)
        raw_name = state.filename or "LIVE STREAM"
        if len(raw_name) > 30:
            display_name = raw_name[:27] + "..."
        else:
            display_name = raw_name

        crt_str = "ON" if state.crt_enabled else "OFF"
        status_str = state.status.upper()

        # Render tokens: Just the clean video name
        x = 12
        y = 5

        name_surf = self.title_font.render(display_name, True, self.COLOR_AMBER)
        screen.blit(name_surf, (x, y))
        x += name_surf.get_width() + 20

        if sw > 500:
            status_surf = self.font.render(f"[{status_str}]", True, self.COLOR_WHITE)
            screen.blit(status_surf, (x, y))
            x += status_surf.get_width() + 18

            crt_tag = self.font.render(f"CRT: {crt_str}", True, self.COLOR_MUTED)
            screen.blit(crt_tag, (x, y))
            x += crt_tag.get_width() + 18

            if not state.has_audio:
                audio_str = "AUDIO: N/A"
            elif not state.audio_enabled:
                audio_str = "AUDIO: MUTE"
            else:
                audio_str = "AUDIO: SYNC"
            sync_tag = self.font.render(audio_str, True, self.COLOR_MUTED)
            screen.blit(sync_tag, (x, y))
            x += sync_tag.get_width() + 18

            loop_str = "ON" if state.loop else "OFF"
            loop_tag = self.font.render(f"LOOP: {loop_str}", True, self.COLOR_MUTED)
            screen.blit(loop_tag, (x, y))

    def draw_gutter(
        self,
        screen: Surface,
        total_rows: int = 0,
        char_height: int = 12,
    ) -> None:
        """Draw left coordinate gutter with vertical row numbers aligned with video rows."""
        sh = screen.get_height()
        gutter_h = max(0, sh - self.HEADER_HEIGHT - self.STATUS_BAR_HEIGHT)
        gutter_rect = pygame.Rect(0, self.HEADER_HEIGHT, self.GUTTER_WIDTH, gutter_h)

        pygame.draw.rect(screen, self.COLOR_GUTTER_BG, gutter_rect)
        pygame.draw.line(
            screen,
            self.COLOR_BORDER,
            (self.GUTTER_WIDTH - 1, self.HEADER_HEIGHT),
            (self.GUTTER_WIDTH - 1, sh - self.STATUS_BAR_HEIGHT),
        )

        ch = max(1, char_height)
        if total_rows > 0:
            num_rows = total_rows
            total_content_h = total_rows * ch
            start_y = self.HEADER_HEIGHT + max(0, (gutter_h - total_content_h) // 2)
        else:
            num_rows = gutter_h // max(8, ch)
            start_y = self.HEADER_HEIGHT

        if ch >= 11:
            step = 1
        elif ch >= 6:
            step = 5
        else:
            step = 10

        for r in range(num_rows):
            y = start_y + r * ch
            if y + ch > sh - self.STATUS_BAR_HEIGHT:
                break
            if y < self.HEADER_HEIGHT:
                continue

            if r % step == 0:
                label = f"{r:03d} |" if num_rows >= 100 else f"{r:02d} |"
                text_surf = self.small_font.render(label, True, self.COLOR_STEEL)
                text_y = y if ch < text_surf.get_height() else y + (ch - text_surf.get_height()) // 2
                screen.blit(text_surf, (6, text_y))
            elif step > 1 and ch >= 4 and (r % (step // 2) == 0):
                tick_surf = self.small_font.render(" · |", True, (45, 55, 70))
                screen.blit(tick_surf, (6, y))

    def draw_status_bar(self, screen: Surface, state: PlayerState) -> None:
        """Draw bottom status bar with zoom, live FPS, speed multiplier and help prompt."""
        sw = screen.get_width()
        sh = screen.get_height()
        status_y = sh - self.STATUS_BAR_HEIGHT
        status_rect = pygame.Rect(0, status_y, sw, self.STATUS_BAR_HEIGHT)

        pygame.draw.rect(screen, self.COLOR_STATUS_BG, status_rect)
        pygame.draw.line(
            screen,
            self.COLOR_BORDER,
            (0, status_y),
            (sw, status_y),
        )

        y = status_y + 5

        # 1. Left: Zoom and Color Mode indicator
        mode_label = state.color_mode.upper() if state.color_mode else "RGB"
        left_txt = f"ZOOM {state.zoom:.1f}x  {mode_label}"
        left_surf = self.small_font.render(left_txt, True, self.COLOR_MUTED)
        screen.blit(left_surf, (12, y))
        left_boundary = 12 + left_surf.get_width() + 16

        # 2. Right: FPS, Speed, and Help prompt
        help_surf = self.font.render("[F1] Help", True, self.COLOR_AMBER)
        speed_surf = self.font.render(f"{state.speed:.2f}x", True, self.COLOR_GREEN)
        fps_surf = self.font.render(f"{state.fps:.1f} fps", True, self.COLOR_GREEN)

        rx = sw - 14
        rx -= help_surf.get_width()
        screen.blit(help_surf, (rx, y))

        rx -= (speed_surf.get_width() + 14)
        if rx > left_boundary + 150:
            screen.blit(speed_surf, (rx, y))

        rx -= (fps_surf.get_width() + 14)
        if rx > left_boundary + 100:
            screen.blit(fps_surf, (rx, y))

        right_boundary = rx - 16

        # 3. Center: Visible Controls Hint directly inside the program
        available_w = right_boundary - left_boundary
        if available_w > 360:
            controls_hint = "[SPACE] Pause | [↑↓] Speed | [C] CRT | [L] Loop | [M] Mute | [F1] Help"
        elif available_w > 260:
            controls_hint = "[SPACE] Pause | [C] CRT | [L] Loop | [M] Mute"
        elif available_w > 160:
            controls_hint = "[SPACE] Pause | [M] Mute | [F1]"
        elif available_w > 90:
            controls_hint = "[SPACE] Pause"
        else:
            controls_hint = ""

        if controls_hint:
            hint_surf = self.small_font.render(controls_hint, True, self.COLOR_STEEL)
            hint_x = left_boundary + (available_w - hint_surf.get_width()) // 2
            if hint_x >= left_boundary and (hint_x + hint_surf.get_width()) <= right_boundary:
                screen.blit(hint_surf, (hint_x, y))

    def draw_help_modal(self, screen: Surface) -> None:
        help_overlay.draw_help_overlay(screen, language=getattr(self, "language", "tr"),
                                       seek_step=getattr(self, "seek_step", 5.0), standalone=False)

    def draw_hud(
        self,
        screen: Surface,
        state: PlayerState,
        total_rows: int = 0,
        char_height: int = 12,
    ) -> None:
        """
        Draw complete HUD chrome (header, coordinate gutter, status bar) and modal.

        Args:
            screen: Destination display surface.
            state: Current player state.
            total_rows: Number of character rows in active ASCII grid.
            char_height: Height of character cells in pixels.
        """
        if getattr(state, "show_hud", False):
            self.draw_header(screen, state)
            self.draw_gutter(screen, total_rows=total_rows, char_height=char_height)
            self.draw_status_bar(screen, state)

        if state.show_help:
            self.draw_help_modal(screen)
