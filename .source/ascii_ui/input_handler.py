"""
Input Handler and Keyboard State Machine for Video-to-ASCII System.

Translates Pygame keyboard, mouse, and window events into non-blocking player
actions and state updates:
- SPACE: Play / Pause toggle
- UP / DOWN: Speed multiplier adjustment (+/- 0.25x between 0.5x and 2.0x)
- LEFT / RIGHT: Time seeking (+/- 5.0 seconds)
- R: Toggle CRT retro post-processing effects
- F1: Toggle help guide modal overlay
- ESC / Q: Exit player
- VIDEORESIZE: Window dimension update callback
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from ascii_ui.hud import PlayerState


class InputHandler:
    """
    Non-blocking keyboard event state machine and Pygame event processor.
    """

    def __init__(
        self,
        on_resize: Callable[[int, int], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        on_seek: Callable[[float], None] | None = None,
        seek_step: float = 5.0,
    ) -> None:
        """
        Initialize the input handler with optional action callbacks.

        Args:
            on_resize: Callback invoked on pygame.VIDEORESIZE with (width, height).
            on_quit: Callback invoked when quit is requested.
            on_seek: Callback invoked when seek target timestamp is changed.
            seek_step: Interval in seconds for left/right seeking (default 5.0).
        """
        self.on_resize = on_resize
        self.on_quit = on_quit
        self.on_seek = on_seek
        self.should_quit: bool = False
        self.seek_step: float = float(seek_step)
        self.last_seek_delta: float = 0.0

    def handle_key(self, key: int, state: PlayerState) -> str | None:
        """
        Process a single keycode and update PlayerState accordingly.

        Args:
            key: Pygame key code (e.g. pygame.K_SPACE).
            state: Current player state to mutate.

        Returns:
            Action name string or None if unhandled.
        """
        if key == pygame.K_SPACE:
            if state.status == "PLAYING":
                state.status = "PAUSED"
            else:
                state.status = "PLAYING"
            return "TOGGLE_PLAY"

        if key == pygame.K_UP:
            state.speed = round(min(2.0, state.speed + 0.25), 2)
            return "SPEED_UP"

        if key == pygame.K_DOWN:
            state.speed = round(max(0.5, state.speed - 0.25), 2)
            return "SPEED_DOWN"

        if key == pygame.K_z:
            steps = [5.0, 10.0, 30.0, 60.0]
            try:
                curr_idx = steps.index(self.seek_step)
                self.seek_step = steps[(curr_idx + 1) % len(steps)]
            except ValueError:
                self.seek_step = 5.0
            return "CYCLE_SEEK"

        if key == pygame.K_LEFT:
            self.last_seek_delta = -self.seek_step
            state.current_time = max(0.0, state.current_time - self.seek_step)
            if self.on_seek:
                self.on_seek(state.current_time)
            return "SEEK_BACKWARD"

        if key == pygame.K_RIGHT:
            self.last_seek_delta = self.seek_step
            if state.duration > 0:
                state.current_time = min(state.duration, state.current_time + self.seek_step)
            else:
                state.current_time += self.seek_step
            if self.on_seek:
                self.on_seek(state.current_time)
            return "SEEK_FORWARD"

        if key in (pygame.K_r, pygame.K_c):
            state.crt_enabled = not state.crt_enabled
            return "TOGGLE_CRT"

        if key == pygame.K_l:
            state.loop = not state.loop
            return "TOGGLE_LOOP"

        if key == pygame.K_t:
            themes = ["truecolor", "grayscale", "green", "amber", "cyberpunk"]
            cur = getattr(state, "color_mode", "truecolor").lower()
            try:
                idx = themes.index(cur)
                next_theme = themes[(idx + 1) % len(themes)]
            except ValueError:
                next_theme = "truecolor"
            state.color_mode = next_theme
            return "CYCLE_THEME"

        if key in (pygame.K_m, pygame.K_s, pygame.K_a):
            state.audio_enabled = not state.audio_enabled
            return "TOGGLE_AUDIO"

        if key in (pygame.K_F1, pygame.K_h):
            state.show_help = not state.show_help
            return "TOGGLE_HELP"

        if key == pygame.K_TAB:
            state.show_hud = not getattr(state, "show_hud", False)
            return "TOGGLE_HUD"

        if key in (pygame.K_ESCAPE, pygame.K_q):
            if getattr(state, "show_help", False):
                state.show_help = False
                return "CLOSE_HELP"
            self.should_quit = True
            state.status = "STOPPED"
            if self.on_quit:
                self.on_quit()
            return "QUIT"

        return None

    def handle_event(self, event: pygame.event.Event, state: PlayerState) -> str | None:
        """
        Process a single Pygame event and update state.

        Args:
            event: Pygame Event instance.
            state: PlayerState to update.

        Returns:
            Action name string or None if unhandled.
        """
        if event.type == pygame.QUIT:
            self.should_quit = True
            state.status = "STOPPED"
            if self.on_quit:
                self.on_quit()
            return "QUIT"

        if event.type == pygame.VIDEORESIZE:
            if self.on_resize:
                self.on_resize(event.w, event.h)
            return "RESIZE"

        if event.type == pygame.KEYDOWN:
            return self.handle_key(event.key, state)

        return None

    def process_events(self, state: PlayerState) -> list[str]:
        """
        Drain all pending events from Pygame queue and update PlayerState.

        Args:
            state: Active PlayerState instance.

        Returns:
            List of triggered action strings.
        """
        actions: list[str] = []
        for event in pygame.event.get():
            action = self.handle_event(event, state)
            if action:
                actions.append(action)
        return actions
