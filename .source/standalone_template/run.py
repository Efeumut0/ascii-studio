#!/usr/bin/env python3
"""Play exported ASCII frames with Pygame and NumPy."""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import sys
import time

try:
    from standalone_template import help_overlay
except ModuleNotFoundError:
    import help_overlay

# Set AppUserModelID on Windows so taskbar uses custom app icon instead of python logo
if sys.platform == "win32":
    with contextlib.suppress(AttributeError, OSError):
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("retro_ascii_studio.app")

    # Hide background CMD/terminal console window cleanly when launched via python/batch
    if not os.environ.get("ASCII_TEST_MODE") and "--headless" not in sys.argv:
        with contextlib.suppress(Exception):
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE = 0

# Pre-set headless drivers before pygame is imported if --headless is supplied
if "--headless" in sys.argv or os.environ.get("SDL_VIDEODRIVER") == "dummy":
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"

try:
    import numpy as np
    import pygame
except ImportError:
    print(
        "[HATA / ERROR] Gerekli kütüphaneler bulunamadı / Required libraries not found: pygame, numpy"
    )
    print(
        "Lütfen yükleyin / Please install: pip install pygame numpy"
    )
    sys.exit(1)


def get_resource_path(relative_path: str) -> str:
    """
    Resolve asset path dynamically for development and PyInstaller bundles.

    Args:
        relative_path: Relative path to resource asset.

    Returns:
        Absolute normalized path to the target asset.
    """
    if hasattr(sys, "_MEIPASS"):
        cand = os.path.join(sys._MEIPASS, relative_path)
        if os.path.exists(cand):
            return cand
    if getattr(sys, "frozen", False):
        exe_cand = os.path.join(os.path.dirname(sys.executable), relative_path)
        if os.path.exists(exe_cand):
            return exe_cand
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, relative_path)


def apply_windows_app_icon(window_surface: pygame.Surface | None = None) -> None:
    """Apply creepy eye icon to Windows process, Pygame window HWND, and console."""
    if sys.platform != "win32":
        return

    import ctypes

    with contextlib.suppress(AttributeError, OSError):
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("retro_ascii_studio.app")

    ico_cands = [
        get_resource_path("eye_icon.ico"),
        get_resource_path("icon.ico"),
        get_resource_path(os.path.join("assets", "eye_icon.ico")),
    ]
    ico_path = next((p for p in ico_cands if os.path.exists(p)), None)

    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x00000010
    WM_SETICON = 0x0080
    ICON_SMALL = 0
    ICON_BIG = 1
    GCLP_HICON = -14
    GCLP_HICONSM = -34

    set_class_long = (
        getattr(ctypes.windll.user32, "SetClassLongPtrW", None)
        or getattr(ctypes.windll.user32, "SetClassLongW", None)
    )

    h_big = None
    h_small = None
    if ico_path:
        with contextlib.suppress(Exception):
            abs_ico = os.path.abspath(ico_path)
            h_big = ctypes.windll.user32.LoadImageW(None, abs_ico, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
            h_small = ctypes.windll.user32.LoadImageW(None, abs_ico, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)

    with contextlib.suppress(Exception):
        info = pygame.display.get_wm_info()
        hwnd = info.get("window")
        if hwnd:
            if h_big:
                ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_big)
                if set_class_long:
                    set_class_long(hwnd, GCLP_HICON, h_big)
            if h_small:
                ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_small)
                if set_class_long:
                    set_class_long(hwnd, GCLP_HICONSM, h_small)

    with contextlib.suppress(Exception):
        hwnd_console = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd_console:
            if h_big:
                ctypes.windll.user32.SendMessageW(hwnd_console, WM_SETICON, ICON_BIG, h_big)
            if h_small:
                ctypes.windll.user32.SendMessageW(hwnd_console, WM_SETICON, ICON_SMALL, h_small)


class StandaloneRenderer:
    """
    Render colored ASCII using cached glyph masks and BLEND_MULT.
    """

    def __init__(
        self,
        font_name: str = "consolas",
        font_size: int = 12,
        char_ramp: str = " .:-=+*#%@",
        color_mode: str = "truecolor",
    ) -> None:
        if not pygame.font.get_init():
            pygame.font.init()

        self.font_name = font_name
        self.font_size = max(3, font_size)
        self.char_ramp = char_ramp if char_ramp else " .:-=+*#%@"
        self.color_mode = color_mode.lower() if color_mode else "truecolor"

        self.font = self._resolve_font(self.font_name, self.font_size)
        self.cw, self.ch = self.font.size("M")
        if self.cw <= 0:
            self.cw = max(1, self.font_size // 2)
        if self.ch <= 0:
            self.ch = max(1, self.font_size)

        # Pre-render 95 printable ASCII glyphs in pure white (255, 255, 255)
        self.glyphs: dict[str, pygame.Surface] = {}
        has_display = pygame.display.get_surface() is not None

        for i in range(32, 127):
            ch = chr(i)
            glyph = self.font.render(ch, False, (255, 255, 255))
            if has_display:
                try:
                    glyph = glyph.convert()
                except pygame.error:
                    pass
            self.glyphs[ch] = glyph

        space_glyph = pygame.Surface((self.cw, self.ch))
        space_glyph.fill((0, 0, 0))
        self.glyphs[" "] = space_glyph

        space_surf = self.glyphs[" "]
        self.ramp_glyphs: list[pygame.Surface] = [
            self.glyphs.get(ch, space_surf) for ch in self.char_ramp
        ]
        self.ascii_glyphs: list[pygame.Surface] = [
            self.glyphs.get(chr(i), space_surf) for i in range(256)
        ]

        self._cached_cols = -1
        self._cached_rows = -1
        self._cached_positions: list[tuple[int, int]] = []
        self._cached_mask: pygame.Surface | None = None

    def set_font_size(self, font_size: int) -> None:
        """Dynamically update font size and re-render glyphs natively at full resolution."""
        target_size = max(3, font_size)
        if target_size == self.font_size and self.glyphs:
            return

        self.font_size = target_size
        self.font = self._resolve_font(self.font_name, self.font_size)
        self.cw, self.ch = self.font.size("M")
        if self.cw <= 0:
            self.cw = max(1, self.font_size // 2)
        if self.ch <= 0:
            self.ch = max(1, self.font_size)

        self.glyphs.clear()
        has_display = pygame.display.get_surface() is not None
        for i in range(32, 127):
            glyph = self.font.render(chr(i), False, (255, 255, 255))
            if has_display:
                try:
                    glyph = glyph.convert()
                except pygame.error:
                    pass
            self.glyphs[chr(i)] = glyph

        space_glyph = pygame.Surface((self.cw, self.ch))
        space_glyph.fill((0, 0, 0))
        self.glyphs[" "] = space_glyph

        space_surf = self.glyphs[" "]
        self.ramp_glyphs = [self.glyphs.get(ch, space_surf) for ch in self.char_ramp]
        self.ascii_glyphs = [self.glyphs.get(chr(i), space_surf) for i in range(256)]

        self._cached_cols = -1
        self._cached_rows = -1
        self._cached_mask = None

    def _resolve_font(self, font_name: str, font_size: int) -> pygame.font.Font:
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

    def set_color_mode(self, mode: str) -> None:
        """Set visual color palette / grading mode."""
        self.color_mode = mode.lower() if mode else "truecolor"

    @staticmethod
    def apply_color_mode(colors: np.ndarray, mode: str) -> np.ndarray:
        """Apply vintage color theme or monochrome grading to RGB matrix."""
        mode = mode.lower() if mode else "truecolor"
        if mode in ("truecolor", "rgb", "color") or not mode:
            return colors

        r = colors[..., 0].astype(np.float32)
        g = colors[..., 1].astype(np.float32)
        b = colors[..., 2].astype(np.float32)
        lum = 0.299 * r + 0.587 * g + 0.114 * b

        if mode in ("grayscale", "bw", "monochrome", "siyah-beyaz", "siyah_beyaz"):
            gray = np.clip(lum, 0, 255).astype(np.uint8)
            return np.stack([gray, gray, gray], axis=-1)

        if mode in ("green", "matrix", "matrix-yesili", "matrix_yesili"):
            norm = lum / 255.0
            out_r = (norm * 15).astype(np.uint8)
            out_g = np.clip(norm * 255, 0, 255).astype(np.uint8)
            out_b = (norm * 55).astype(np.uint8)
            return np.stack([out_r, out_g, out_b], axis=-1)

        if mode in ("amber", "amber-terminali", "amber_terminali"):
            norm = lum / 255.0
            out_r = np.clip(norm * 255, 0, 255).astype(np.uint8)
            out_g = np.clip(norm * 176, 0, 255).astype(np.uint8)
            out_b = (norm * 10).astype(np.uint8)
            return np.stack([out_r, out_g, out_b], axis=-1)

        if mode in ("cyberpunk", "cyberpunk-neon", "cyberpunk_neon", "neon"):
            norm = lum / 255.0
            out_r = np.clip(norm * 240, 0, 255).astype(np.uint8)
            out_g = np.clip(norm * 70 + 20, 0, 255).astype(np.uint8)
            out_b = np.clip(norm * 255, 0, 255).astype(np.uint8)
            return np.stack([out_r, out_g, out_b], axis=-1)

        return colors

    def render_frame(
        self,
        screen: pygame.Surface,
        char_indices: np.ndarray,
        colors: np.ndarray,
        dest_rect: pygame.Rect | tuple[int, int, int, int] | None = None,
    ) -> None:
        if char_indices is None or colors is None:
            return

        rows, cols = char_indices.shape[:2]
        w = cols * self.cw
        h = rows * self.ch

        if cols != self._cached_cols or rows != self._cached_rows or self._cached_mask is None:
            self._cached_cols = cols
            self._cached_rows = rows
            self._cached_positions = [
                (c * self.cw, r * self.ch) for r in range(rows) for c in range(cols)
            ]
            mask_surf = pygame.Surface((w, h))
            if pygame.display.get_surface() is not None:
                try:
                    mask_surf = mask_surf.convert()
                except pygame.error:
                    pass
            self._cached_mask = mask_surf

        mask_surf = self._cached_mask
        mask_surf.fill((0, 0, 0))

        flat = char_indices.ravel()
        max_val = int(np.max(flat)) if flat.size > 0 else 0
        min_val = int(np.min(flat)) if flat.size > 0 else 0
        flat_list = flat.tolist()

        if 0 <= min_val and max_val < len(self.ramp_glyphs):
            lut = self.ramp_glyphs
            blit_list = [
                (lut[idx], pos)
                for idx, pos in zip(flat_list, self._cached_positions)
            ]
        elif 0 <= min_val and max_val < len(self.ascii_glyphs):
            lut = self.ascii_glyphs
            blit_list = [
                (lut[idx], pos)
                for idx, pos in zip(flat_list, self._cached_positions)
            ]
        else:
            space_surf = self.glyphs[" "]
            blit_list = [
                (
                    self.ramp_glyphs[idx] if 0 <= idx < len(self.ramp_glyphs) else space_surf,
                    pos,
                )
                for idx, pos in zip(flat_list, self._cached_positions)
            ]

        mask_surf.blits(blit_list, doreturn=False)

        # Truecolor canvas construction
        if colors.ndim == 3 and colors.shape[2] == 4:
            colors = colors[..., :3]

        if self.color_mode and self.color_mode not in ("truecolor", "rgb", "color"):
            colors = self.apply_color_mode(colors, self.color_mode)

        if not colors.flags.c_contiguous:
            colors = np.ascontiguousarray(colors)

        color_surf = pygame.image.frombuffer(colors.data, (cols, rows), "RGB")
        scaled_color = pygame.transform.scale(color_surf, (w, h))
        scaled_color.blit(mask_surf, (0, 0), special_flags=pygame.BLEND_MULT)

        if dest_rect is None:
            screen.blit(scaled_color, (0, 0))
        else:
            # Blit with native 1:1 sharpness or downscale if exceeding viewport
            if isinstance(dest_rect, pygame.Rect):
                dx, dy, dw, dh = dest_rect.x, dest_rect.y, dest_rect.w, dest_rect.h
            else:
                dx, dy, dw, dh = dest_rect

            if w <= dw and h <= dh:
                # 1:1 Native pixel sharpness: zero scaling, zero blur, centered
                offset_x = dx + (dw - w) // 2
                offset_y = dy + (dh - h) // 2
                screen.blit(scaled_color, (offset_x, offset_y))
            elif dw > 0 and dh > 0:
                scale = min(dw / w, dh / h)
                fit_w = max(1, int(w * scale))
                fit_h = max(1, int(h * scale))
                offset_x = dx + (dw - fit_w) // 2
                offset_y = dy + (dh - fit_h) // 2
                fit_surf = pygame.transform.scale(scaled_color, (fit_w, fit_h))
                screen.blit(fit_surf, (offset_x, offset_y))
            else:
                screen.blit(scaled_color, (dx, dy))


class StandaloneCrtEffect:
    """
    Vintage CRT post-processing effect: scanlines, phosphor bloom, and radial vignette.
    """

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self.width = max(1, width)
        self.height = max(1, height)
        self.scanlines_surf: pygame.Surface | None = None
        self.vignette_surf: pygame.Surface | None = None
        self.resize(self.width, self.height)

    def resize(self, width: int, height: int) -> None:
        self.width = max(1, width)
        self.height = max(1, height)

        # 1. Pre-render scanlines alpha mask
        scanlines = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        for y in range(0, self.height, 2):
            scanlines.fill((0, 0, 0, 60), rect=pygame.Rect(0, y, self.width, 1))
        self.scanlines_surf = scanlines

        # 2. Pre-render radial vignette mask
        low_w = max(4, min(160, self.width))
        low_h = max(4, min(90, self.height))

        xs = np.linspace(-1.0, 1.0, low_w, dtype=np.float32)
        ys = np.linspace(-1.0, 1.0, low_h, dtype=np.float32)
        xg, yg = np.meshgrid(xs, ys)
        dist_sq = xg**2 + yg**2

        alpha = np.clip((dist_sq - 0.4) / 0.8 * 140.0, 0, 140).astype(np.uint8)
        low_surf = pygame.Surface((low_w, low_h), pygame.SRCALPHA)
        low_surf.fill((0, 0, 0, 0))
        alpha_t = np.transpose(alpha, (1, 0))
        alpha_view = pygame.surfarray.pixels_alpha(low_surf)
        alpha_view[:] = alpha_t
        del alpha_view, alpha_t

        self.vignette_surf = pygame.transform.smoothscale(low_surf, (self.width, self.height))

    def apply(self, screen: pygame.Surface, crt_enabled: bool = True, bloom: bool = False) -> None:
        if not crt_enabled:
            return

        sw, sh = screen.get_size()
        if sw != self.width or sh != self.height:
            self.resize(sw, sh)

        # 1. Optional bloom
        if bloom:
            down_w = max(4, self.width // 8)
            down_h = max(4, self.height // 8)
            small = pygame.transform.scale(screen, (down_w, down_h))
            glow = pygame.transform.smoothscale(small, (max(8, self.width // 4), max(8, self.height // 4)))
            bloom_surf = pygame.transform.scale(glow, (self.width, self.height))
            screen.blit(bloom_surf, (0, 0), special_flags=pygame.BLEND_ADD)

        # 2. Scanlines
        if self.scanlines_surf is not None:
            screen.blit(self.scanlines_surf, (0, 0))

        # 3. Vignette
        if self.vignette_surf is not None:
            screen.blit(self.vignette_surf, (0, 0))


class StandaloneHudRenderer:
    """
    Renders retro chrome HUD: top header, left coordinate gutter, bottom status bar,
    and centered [F1] help modal overlay.
    """

    HEADER_HEIGHT = 28
    GUTTER_WIDTH = 48
    STATUS_BAR_HEIGHT = 28

    COLOR_HEADER_BG = (15, 15, 20)
    COLOR_GUTTER_BG = (12, 12, 16)
    COLOR_STATUS_BG = (15, 15, 20)
    COLOR_BORDER = (50, 55, 70)
    COLOR_AMBER = (255, 200, 50)
    COLOR_STEEL = (80, 95, 110)
    COLOR_MUTED = (160, 165, 180)
    COLOR_GREEN = (100, 230, 130)
    COLOR_WHITE = (235, 238, 245)
    COLOR_MODAL_BG = (16, 20, 28)
    COLOR_MODAL_BORDER = (80, 180, 120)

    def __init__(self, font_name: str = "consolas", font_size: int = 14) -> None:
        if not pygame.font.get_init():
            pygame.font.init()

        self.font = self._resolve_font(font_name, font_size)
        self.small_font = self._resolve_font(font_name, max(9, font_size - 2))
        self.modal_font = self._resolve_font(font_name, font_size)
        self.title_font = self._resolve_font(font_name, font_size + 2)

    def _resolve_font(self, font_name: str, font_size: int) -> pygame.font.Font:
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

    def draw_header(
        self,
        screen: pygame.Surface,
        filename: str,
        status: str,
        crt_enabled: bool,
        loop_enabled: bool = False,
        has_audio: bool = True,
        audio_enabled: bool = True,
    ) -> None:
        sw = screen.get_width()
        header_rect = pygame.Rect(0, 0, sw, self.HEADER_HEIGHT)
        pygame.draw.rect(screen, self.COLOR_HEADER_BG, header_rect)
        pygame.draw.line(
            screen,
            self.COLOR_BORDER,
            (0, self.HEADER_HEIGHT - 1),
            (sw, self.HEADER_HEIGHT - 1),
        )

        display_name = filename if len(filename) <= 30 else filename[:27] + "..."
        crt_str = "ON" if crt_enabled else "OFF"
        status_str = status.upper()

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

            if not has_audio:
                audio_str = "AUDIO: N/A"
            elif not audio_enabled:
                audio_str = "AUDIO: MUTE"
            else:
                audio_str = "AUDIO: SYNC"
            sync_tag = self.font.render(audio_str, True, self.COLOR_MUTED)
            screen.blit(sync_tag, (x, y))
            x += sync_tag.get_width() + 18

            loop_str = "ON" if loop_enabled else "OFF"
            loop_tag = self.font.render(f"LOOP: {loop_str}", True, self.COLOR_MUTED)
            screen.blit(loop_tag, (x, y))

    def draw_gutter(
        self,
        screen: pygame.Surface,
        total_rows: int = 0,
        char_height: int = 12,
    ) -> None:
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

    def draw_status_bar(
        self,
        screen: pygame.Surface,
        fps: float,
        speed: float,
        current_time: float,
        duration: float,
    ) -> None:
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

        # Left info
        left_txt = "ZOOM 1.0x  RGB"
        left_surf = self.small_font.render(left_txt, True, self.COLOR_MUTED)
        screen.blit(left_surf, (12, y))
        left_boundary = 12 + left_surf.get_width() + 16

        # Right info
        cur_min = int(current_time) // 60
        cur_sec = int(current_time) % 60
        dur_min = int(duration) // 60
        dur_sec = int(duration) % 60
        time_str = f"{cur_min:02d}:{cur_sec:02d} / {dur_min:02d}:{dur_sec:02d}"

        time_surf = self.font.render(time_str, True, self.COLOR_WHITE)
        speed_surf = self.font.render(f"{speed:.2f}x", True, self.COLOR_GREEN)
        fps_surf = self.font.render(f"{fps:.1f} fps", True, self.COLOR_GREEN)

        rx = sw - 12
        rx -= time_surf.get_width()
        screen.blit(time_surf, (rx, y))

        rx -= (speed_surf.get_width() + 14)
        if rx > left_boundary + 150:
            screen.blit(speed_surf, (rx, y))

        rx -= (fps_surf.get_width() + 14)
        if rx > left_boundary + 100:
            screen.blit(fps_surf, (rx, y))

        right_boundary = rx - 16

        # Center info: Prominent Controls Hint directly on screen
        available_w = right_boundary - left_boundary
        if available_w > 320:
            controls_hint = "[SPACE] Pause | [↑↓] Speed | [C] CRT | [L] Loop | [F1] Help"
        elif available_w > 200:
            controls_hint = "[SPACE] Pause | [↑↓] Speed | [F1]"
        elif available_w > 90:
            controls_hint = "[SPACE] Pause"
        else:
            controls_hint = ""

        if controls_hint:
            hint_surf = self.small_font.render(controls_hint, True, self.COLOR_STEEL)
            hint_x = left_boundary + (available_w - hint_surf.get_width()) // 2
            if hint_x >= left_boundary and (hint_x + hint_surf.get_width()) <= right_boundary:
                screen.blit(hint_surf, (hint_x, y))

    def draw_help_modal(self, screen: pygame.Surface, seek_step: float = 5.0) -> None:
        help_overlay.draw_help_overlay(screen, language=getattr(self, "language", "tr"),
                                       seek_step=seek_step, standalone=True)


def main() -> int:
    """Run standalone ASCII player."""
    parser = argparse.ArgumentParser(
        description="Standalone Retro ASCII Video Player (pygame + numpy only)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.json file (defaults to bundled config.json)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run player in headless mode (dummy SDL video/audio)",
    )
    parser.add_argument(
        "--fullscreen",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Start in clean fullscreen presentation mode (default: False)",
    )
    parser.add_argument(
        "--hud",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Show HUD chrome header, gutter, and footer (default: False for clean fullscreen video)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Maximum playback duration in seconds before terminating",
    )
    parser.add_argument(
        "--loop",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Loop playback indefinitely from beginning",
    )
    parser.add_argument(
        "--crt",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable CRT post-processing",
    )
    parser.add_argument(
        "--audio",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable or disable audio playback (use --no-audio to mute)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Initial playback speed multiplier",
    )
    parser.add_argument(
        "--color-mode",
        type=str,
        default=None,
        help="Color theme / grading mode ('truecolor', 'grayscale', 'green', 'amber', 'cyberpunk')",
    )
    parser.add_argument(
        "--seek-step",
        type=float,
        default=None,
        help="Interval in seconds for left/right seeking (defaults to config.json)",
    )
    args = parser.parse_args()

    # 1. Resolve config path
    config_file = args.config if args.config else get_resource_path("config.json")
    if not os.path.exists(config_file):
        print(f"[HATA / ERROR] Yapılandırma dosyası bulunamadı / Config file not found: {config_file}")
        return 1

    config_dir = os.path.dirname(os.path.abspath(config_file))

    def resolve_asset(rel_name: str) -> str:
        if not rel_name:
            return ""
        if os.path.isabs(rel_name) and os.path.exists(rel_name):
            return rel_name
        res_cand = get_resource_path(rel_name)
        if os.path.exists(res_cand):
            return res_cand
        cfg_cand = os.path.join(config_dir, rel_name)
        if os.path.exists(cfg_cand):
            return cfg_cand
        return res_cand

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise TypeError("Config must be a JSON object")
        fps = float(cfg.get("fps", 30.0))
        total_frames = int(cfg.get("total_frames", 0))
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("FPS must be finite and greater than zero")
        duration = float(cfg.get("duration_seconds", total_frames / fps))
        cfg_seek_step = float(cfg.get("seek_step", 5.0))
        if not math.isfinite(duration) or duration < 0 or total_frames < 0:
            raise ValueError("Duration and frame count must be non-negative")
        if not math.isfinite(cfg_seek_step) or cfg_seek_step <= 0:
            raise ValueError("Seek step must be finite and greater than zero")
        aspect_ratio = float(cfg.get("aspect_ratio", 0))
        if not math.isfinite(aspect_ratio) or aspect_ratio < 0:
            raise ValueError("Aspect ratio must be finite and non-negative")
        requested_font_size = int(cfg.get("font_size", 0))
        if requested_font_size != 0 and not 3 <= requested_font_size <= 48:
            raise ValueError("Font size must be automatic or between 3 and 48")
        for asset_key in ("audio_file", "data_file", "colors_file"):
            if asset_key in cfg and not isinstance(cfg[asset_key], str):
                raise ValueError(f"{asset_key} must be a path string")
        ramp = cfg.get("char_ramp", " .:-=+*#%@")
        if not isinstance(ramp, str) or not 1 <= len(ramp) <= 256:
            raise ValueError("char_ramp must contain between 1 and 256 characters")
    except (ValueError, TypeError, OverflowError, OSError) as exc:
        print(f"[HATA / ERROR] Yapılandırma dosyası okunamadı / Failed reading config: {exc}")
        return 1

    source_video = cfg.get("source_video", "video")
    cols = cfg.get("cols", 80)
    rows = cfg.get("rows", 60)
    cfg_audio_enabled = bool(cfg.get("audio_enabled", True))
    has_audio = bool(cfg.get("has_audio", False)) and args.audio and cfg_audio_enabled
    audio_file_rel = cfg.get("audio_file", "audio.wav")
    data_file_rel = cfg.get("data_file", "ascii_data.npz")
    char_ramp = cfg.get("char_ramp", " .:-=+*#%@")
    color_mode = args.color_mode if args.color_mode is not None else cfg.get("color_mode", "truecolor")
    crt_enabled = args.crt if args.crt is not None else bool(cfg.get("crt_default", False))
    loop_enabled = args.loop if args.loop is not None else bool(cfg.get("loop_default", False))
    seek_step = float(args.seek_step if args.seek_step is not None else cfg_seek_step)
    seek_steps = [5.0, 10.0, 30.0, 60.0]
    window_title = cfg.get("window_title", f"ASCII Retro Player - {source_video}")

    # Fullscreen & clean mode configuration (default windowed mode without HUD chrome)
    fullscreen_default = bool(cfg.get("fullscreen_default", False))
    is_fullscreen = args.fullscreen if args.fullscreen is not None else fullscreen_default
    show_hud = args.hud if args.hud is not None else bool(cfg.get("show_hud", False))

    # 2. Resolve and load ascii_data.npz
    data_file = resolve_asset(data_file_rel)
    if not os.path.exists(data_file):
        print(f"[HATA / ERROR] ASCII veri dosyası bulunamadı / ASCII data not found: {data_file}")
        return 1

    try:
        if data_file.lower().endswith(".npy"):
            all_chars = np.load(data_file, mmap_mode="r", allow_pickle=False)
            all_colors = np.load(resolve_asset(cfg.get("colors_file", "colors.npy")), mmap_mode="r", allow_pickle=False)
        else:
            with np.load(data_file) as npz_data:
                all_chars = np.array(npz_data["chars"], copy=True)
                all_colors = np.array(npz_data["colors"], copy=True)
    except (OSError, ValueError, KeyError) as exc:
        print(f"[HATA / ERROR] ASCII verisi yüklenemedi / Failed loading ASCII dataset: {exc}")
        return 1

    if (
        all_chars.ndim != 3
        or all_colors.shape != (*all_chars.shape, 3)
        or all_chars.dtype != np.uint8
        or all_colors.dtype != np.uint8
        or not all(all_chars.shape)
    ):
        print("[HATA / ERROR] ASCII verisi geçersiz / Invalid ASCII dataset dimensions or dtype")
        return 1

    total_frames = all_chars.shape[0]
    rows, cols = all_chars.shape[1], all_chars.shape[2]
    if duration <= 0:
        duration = total_frames / fps

    # 3. Initialize Pygame & Mixer
    pygame.init()
    pygame.font.init()

    audio_loaded = False
    if has_audio and audio_file_rel:
        audio_path = resolve_asset(audio_file_rel)
        if os.path.exists(audio_path):
            try:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
                pygame.mixer.music.load(audio_path)
                audio_loaded = True
            except (pygame.error, OSError) as exc:
                print(f"[UYARI / WARNING] Ses başlatılamadı / Failed loading audio: {exc}")
                audio_loaded = False
        else:
            audio_loaded = False

    # 4. Query desktop resolution & configure display
    info = pygame.display.Info()
    desktop_w = info.current_w if info.current_w > 0 else 1920
    desktop_h = info.current_h if info.current_h > 0 else 1080

    def compute_optimal_font_size(w: int, h: int, with_hud: bool) -> int:
        gw = StandaloneHudRenderer.GUTTER_WIDTH if with_hud else 0
        hh = StandaloneHudRenderer.HEADER_HEIGHT if with_hud else 0
        fh = StandaloneHudRenderer.STATUS_BAR_HEIGHT if with_hud else 0
        avail_w = max(20, w - gw)
        avail_h = max(20, h - hh - fh)
        target_cw = max(1, avail_w // cols)
        target_ch = max(1, avail_h // rows)
        for fs in range(64, 2, -1):
            tf = pygame.font.SysFont("consolas", fs)
            tcw, tch = tf.size("M")
            if tcw <= target_cw and tch <= target_ch:
                return fs
        return 3

    # Set custom creepy eye icon BEFORE set_mode so Windows uses it for taskbar and titlebar
    icon_path = resolve_asset("eye_icon.png")
    if not os.path.exists(icon_path):
        icon_path = resolve_asset("icon.png")
    if os.path.exists(icon_path):
        try:
            icon_surf = pygame.image.load(icon_path)
            pygame.display.set_icon(icon_surf)
        except (pygame.error, OSError):
            pass

    v_aspect = aspect_ratio or (cols * 0.55) / max(1, rows)
    if is_fullscreen:
        try:
            screen = pygame.display.set_mode((desktop_w, desktop_h), pygame.FULLSCREEN | pygame.DOUBLEBUF)
            win_w, win_h = desktop_w, desktop_h
        except pygame.error:
            if v_aspect >= 1.0:
                win_w = min(1280, max(640, int(desktop_w * 0.70)))
                win_h = max(360, min(int(desktop_h * 0.85), int(win_w / v_aspect)))
            else:
                win_h = min(960, max(600, int(desktop_h * 0.75)))
                win_w = max(360, min(int(desktop_w * 0.60), int(win_h * v_aspect)))
            screen = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE)
            is_fullscreen = False
    else:
        if v_aspect >= 1.0:
            win_w = min(1280, max(640, int(desktop_w * 0.70)))
            win_h = max(360, min(int(desktop_h * 0.85), int(win_w / v_aspect)))
        else:
            win_h = min(960, max(600, int(desktop_h * 0.75)))
            win_w = max(360, min(int(desktop_w * 0.60), int(win_h * v_aspect)))
        screen = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE)

    apply_windows_app_icon(screen)

    actual_fs = requested_font_size or compute_optimal_font_size(win_w, win_h, show_hud)

    renderer = StandaloneRenderer(
        font_name="consolas",
        font_size=actual_fs,
        char_ramp=char_ramp,
        color_mode=color_mode,
    )
    hud = StandaloneHudRenderer(font_name="consolas", font_size=max(12, actual_fs + 1))
    hud.language = cfg.get("language", "tr")

    display_title = source_video or window_title
    pygame.display.set_caption(display_title)

    crt_effect = StandaloneCrtEffect(win_w, win_h)

    # 5. Playback State
    playing = True
    speed = max(0.5, min(2.0, args.speed))
    show_help = False
    current_frame = 0

    master_time = 0.0
    start_offset = 0.0
    play_start_perf = time.perf_counter()
    wall_start = time.perf_counter()

    if audio_loaded:
        try:
            pygame.mixer.music.play()
        except pygame.error:
            pass

    clock = pygame.time.Clock()
    fps_history: list[float] = []
    last_frame_time = time.perf_counter()

    def get_current_master_time() -> float:
        nonlocal play_start_perf, start_offset, master_time
        if playing:
            elapsed = (time.perf_counter() - play_start_perf) * speed
            return start_offset + elapsed
        return master_time

    # 6. Main Interactive Loop
    running = True
    while running:
        # Check maximum duration if specified (e.g. for testing)
        if args.duration is not None and (time.perf_counter() - wall_start) >= args.duration:
            break

        # Event handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break
            elif event.type == pygame.VIDEORESIZE:
                win_w, win_h = max(400, event.w), max(300, event.h)
                screen = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE)
                crt_effect.resize(win_w, win_h)
                renderer.set_font_size(compute_optimal_font_size(win_w, win_h, show_hud))
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    if show_help:
                        show_help = False
                    elif show_hud:
                        show_hud = False
                    else:
                        running = False
                        break
                elif event.key in (pygame.K_f, pygame.K_F11):
                    # Toggle Fullscreen / Windowed
                    is_fullscreen = not is_fullscreen
                    if is_fullscreen:
                        try:
                            screen = pygame.display.set_mode((desktop_w, desktop_h), pygame.FULLSCREEN | pygame.DOUBLEBUF)
                            win_w, win_h = desktop_w, desktop_h
                        except pygame.error:
                            is_fullscreen = False
                    else:
                        if v_aspect >= 1.0:
                            win_w = min(1280, max(640, int(desktop_w * 0.70)))
                            win_h = max(360, min(int(desktop_h * 0.85), int(win_w / v_aspect)))
                        else:
                            win_h = min(960, max(600, int(desktop_h * 0.75)))
                            win_w = max(360, min(int(desktop_w * 0.60), int(win_h * v_aspect)))
                        screen = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE)
                    apply_windows_app_icon(screen)
                    crt_effect.resize(win_w, win_h)
                    renderer.set_font_size(compute_optimal_font_size(win_w, win_h, show_hud))
                elif event.key in (pygame.K_h, pygame.K_F1):
                    # Toggle Help Modal overlay (clean presentation preserved underneath)
                    show_help = not show_help
                elif event.key == pygame.K_z:
                    # Cycle seek step interval
                    try:
                        s_idx = seek_steps.index(seek_step)
                        seek_step = seek_steps[(s_idx + 1) % len(seek_steps)]
                    except ValueError:
                        seek_step = 5.0
                elif event.key in (pygame.K_s, pygame.K_m, pygame.K_a):
                    # Toggle Audio Mute
                    if audio_loaded:
                        try:
                            vol = pygame.mixer.music.get_volume()
                            pygame.mixer.music.set_volume(0.0 if vol > 0.0 else 1.0)
                        except pygame.error:
                            pass
                elif event.key == pygame.K_SPACE:
                    if playing:
                        # Pause
                        master_time = get_current_master_time()
                        playing = False
                        if audio_loaded:
                            try:
                                pygame.mixer.music.pause()
                            except pygame.error:
                                pass
                    else:
                        # Resume
                        playing = True
                        start_offset = master_time
                        play_start_perf = time.perf_counter()
                        if audio_loaded and speed == 1.0:
                            try:
                                pygame.mixer.music.play(loops=0, start=start_offset)
                            except pygame.error:
                                pass
                elif event.key == pygame.K_UP:
                    # Speed up: recalculate timing baseline seamlessly with 0 freeze
                    now_t = get_current_master_time()
                    master_time = min(duration, max(0.0, now_t))
                    start_offset = master_time
                    play_start_perf = time.perf_counter()
                    speed = round(min(2.0, speed + 0.25), 2)
                    if audio_loaded:
                        if speed != 1.0:
                            try:
                                pygame.mixer.music.pause()
                            except pygame.error:
                                pass
                        elif playing:
                            try:
                                pygame.mixer.music.play(loops=0, start=master_time)
                            except pygame.error:
                                pass
                elif event.key == pygame.K_DOWN:
                    # Speed down: recalculate timing baseline seamlessly with 0 freeze
                    now_t = get_current_master_time()
                    master_time = min(duration, max(0.0, now_t))
                    start_offset = master_time
                    play_start_perf = time.perf_counter()
                    speed = round(max(0.5, speed - 0.25), 2)
                    if audio_loaded:
                        if speed != 1.0:
                            try:
                                pygame.mixer.music.pause()
                            except pygame.error:
                                pass
                        elif playing:
                            try:
                                pygame.mixer.music.play(loops=0, start=master_time)
                            except pygame.error:
                                pass
                elif event.key == pygame.K_RIGHT:
                    # Seek forward by seek_step
                    cur_t = get_current_master_time()
                    new_t = min(duration, cur_t + seek_step)
                    master_time = new_t
                    start_offset = new_t
                    play_start_perf = time.perf_counter()
                    if audio_loaded and speed == 1.0 and playing:
                        try:
                            pygame.mixer.music.play(loops=0, start=new_t)
                        except pygame.error:
                            pass
                elif event.key == pygame.K_LEFT:
                    # Seek backward by seek_step
                    cur_t = get_current_master_time()
                    new_t = max(0.0, cur_t - seek_step)
                    master_time = new_t
                    start_offset = new_t
                    play_start_perf = time.perf_counter()
                    if audio_loaded and speed == 1.0 and playing:
                        try:
                            pygame.mixer.music.play(loops=0, start=new_t)
                        except pygame.error:
                            pass
                elif event.key in (pygame.K_r, pygame.K_c):
                    crt_enabled = not crt_enabled
                elif event.key == pygame.K_t:
                    themes = ["truecolor", "grayscale", "green", "amber", "cyberpunk"]
                    cur_cm = getattr(renderer, "color_mode", "truecolor").lower()
                    try:
                        t_idx = themes.index(cur_cm)
                        next_cm = themes[(t_idx + 1) % len(themes)]
                    except ValueError:
                        next_cm = "truecolor"
                    renderer.set_color_mode(next_cm)
                elif event.key == pygame.K_l:
                    loop_enabled = not loop_enabled

        if not running:
            break

        # Clock calculation & Frame Synchronization
        if playing:
            cur_time = get_current_master_time()
            if cur_time >= duration or (fps > 0 and int(cur_time * fps) >= total_frames):
                if loop_enabled:
                    # Loop video
                    start_offset = 0.0
                    play_start_perf = time.perf_counter()
                    master_time = 0.0
                    current_frame = 0
                    if audio_loaded:
                        try:
                            pygame.mixer.music.play()
                        except pygame.error:
                            pass
                else:
                    # End of stream
                    current_frame = total_frames - 1
                    master_time = duration
                    playing = False
                    if audio_loaded:
                        try:
                            pygame.mixer.music.pause()
                        except pygame.error:
                            pass
            else:
                target_frame = int(cur_time * fps)
                current_frame = max(0, min(total_frames - 1, target_frame))
                master_time = cur_time
        else:
            # Paused
            current_frame = max(0, min(total_frames - 1, int(master_time * fps)))

        # FPS calculation
        now = time.perf_counter()
        dt = now - last_frame_time
        last_frame_time = now
        if dt > 0:
            fps_history.append(1.0 / dt)
            if len(fps_history) > 30:
                fps_history.pop(0)
        curr_fps = sum(fps_history) / len(fps_history) if fps_history else fps

        # Screen rendering on pure black canvas
        screen.fill((0, 0, 0))

        # Viewport layout with dynamic window dimensions (zero margin if show_hud is False)
        cur_w, cur_h = screen.get_size()
        gw = StandaloneHudRenderer.GUTTER_WIDTH if show_hud else 0
        hh = StandaloneHudRenderer.HEADER_HEIGHT if show_hud else 0
        fh = StandaloneHudRenderer.STATUS_BAR_HEIGHT if show_hud else 0

        avail_w = max(10, cur_w - gw)
        avail_h = max(10, cur_h - hh - fh)
        viewport_rect = pygame.Rect(gw, hh, avail_w, avail_h)

        # 1. Render ASCII Frame with native 1:1 sharpness
        frame_chars = all_chars[current_frame]
        frame_colors = all_colors[current_frame]
        renderer.render_frame(screen, frame_chars, frame_colors, viewport_rect)

        # 2. Apply CRT scanlines, vignette & bloom
        crt_effect.apply(screen, crt_enabled=crt_enabled)

        # 3. Draw HUD Chrome only if user explicitly toggled it on
        if show_hud:
            status_text = "PAUSED" if not playing else "PLAYING"
            hud.draw_header(screen, source_video, status_text, crt_enabled, loop_enabled, has_audio, audio_loaded)
            hud.draw_gutter(screen, total_rows=rows, char_height=renderer.ch)
            hud.draw_status_bar(screen, curr_fps, speed, master_time, duration)

        # 4. Draw Help Modal overlay whenever active (clean presentation underneath)
        if show_help:
            hud.draw_help_modal(screen, seek_step=seek_step)

        pygame.display.flip()
        clock.tick(max(60, int(fps * 2)))

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
