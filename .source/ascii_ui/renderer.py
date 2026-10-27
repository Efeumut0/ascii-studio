"""Render colored ASCII with cached glyph masks."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import TYPE_CHECKING

import cv2
import numpy as np
import pygame

if TYPE_CHECKING:
    from pygame import Rect, Surface


DEFAULT_RAMP = " .:-=+*#%@"
CLASSIC_16_RAMP = " .:-=+*#%@#%&WM"
DETAILED_RAMP = " .'`^\",:;Il!i~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
EXTENDED_92_RAMP = " `.`-':_\",^=;><+!rc*/z?sLTv)J7(|Fi{C}fI31tlu[neoZ5Yxjya]2ESwqkP6h9d4VpOGbUAKXHm8RD#$Bg0MNWQ%&@"


class AsciiRenderer:
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
        """
        Initialize the ASCII renderer with monospace font, character ramp, and color mode.

        Args:
            font_name: Font family name or TTF file path.
            font_size: Font size in points.
            char_ramp: String of characters ordered by increasing luminance.
            color_mode: Color grading mode ('truecolor', 'grayscale', 'green', 'amber', 'cyberpunk').
        """
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

        # Pre-render 95 printable ASCII glyphs (32..126) in pure white (255, 255, 255)
        self.glyphs: dict[str, Surface] = {}
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

        # Fallback space glyph
        if " " not in self.glyphs:
            space_glyph = pygame.Surface((self.cw, self.ch))
            space_glyph.fill((0, 0, 0))
            self.glyphs[" "] = space_glyph

        space_surf = self.glyphs[" "]
        self.ramp_glyphs: list[Surface] = [
            self.glyphs.get(ch, space_surf) for ch in self.char_ramp
        ]
        self.ascii_glyphs: list[Surface] = [
            self.glyphs.get(chr(i), space_surf) for i in range(256)
        ]

        # Dynamic cache for grid dimensions and blit coordinate list
        self._cached_cols = -1
        self._cached_rows = -1
        self._cached_positions: list[tuple[int, int]] = []
        self._cached_mask: Surface | None = None

        # Pre-rendered 2D, 1-bit, and 255-scaled glyph stacks for vectorized rasterization
        self._cached_ramp_stack_2d: np.ndarray | None = None
        self._cached_ramp_stack_1bit: np.ndarray | None = None
        self._cached_ramp_stack_255: np.ndarray | None = None
        self._cached_ascii_stack_2d: np.ndarray | None = None
        self._cached_ascii_stack_1bit: np.ndarray | None = None
        self._cached_ascii_stack_255: np.ndarray | None = None
        self._init_glyph_stacks()

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
        self._init_glyph_stacks()

    def _init_glyph_stacks(self) -> None:
        """Pre-render 2D, 1-bit, and 255-scaled glyph arrays for fast vectorized blitting and direct rasterization."""
        ramp_cells = []
        ramp_1bit = []
        ramp_255 = []
        for g in self.ramp_glyphs:
            cs = pygame.Surface((self.cw, self.ch))
            cs.fill((0, 0, 0))
            cs.blit(g, (0, 0))
            ramp_cells.append(pygame.surfarray.array2d(cs))
            arr_3d = pygame.surfarray.array3d(cs)
            mask_1bit = (arr_3d[..., 0] > 128).T.astype(np.uint8)
            ramp_1bit.append(mask_1bit)
            ramp_255.append(mask_1bit * 255)

        blank_255 = np.zeros((self.ch, self.cw), dtype=np.uint8)
        ramp_255_with_blank = list(ramp_255) + [blank_255]

        self._cached_ramp_stack_2d = np.stack(ramp_cells, axis=0) if ramp_cells else None
        self._cached_ramp_stack_1bit = np.stack(ramp_1bit, axis=0) if ramp_1bit else None
        self._cached_ramp_stack_255 = np.stack(ramp_255_with_blank, axis=0) if ramp_255 else None

        ascii_cells = []
        ascii_1bit = []
        ascii_255 = []
        for g in self.ascii_glyphs:
            cs = pygame.Surface((self.cw, self.ch))
            cs.fill((0, 0, 0))
            cs.blit(g, (0, 0))
            ascii_cells.append(pygame.surfarray.array2d(cs))
            arr_3d = pygame.surfarray.array3d(cs)
            mask_1bit = (arr_3d[..., 0] > 128).T.astype(np.uint8)
            ascii_1bit.append(mask_1bit)
            ascii_255.append(mask_1bit * 255)

        ascii_255_with_blank = list(ascii_255) + [blank_255]

        self._cached_ascii_stack_2d = np.stack(ascii_cells, axis=0) if ascii_cells else None
        self._cached_ascii_stack_1bit = np.stack(ascii_1bit, axis=0) if ascii_1bit else None
        self._cached_ascii_stack_255 = np.stack(ascii_255_with_blank, axis=0) if ascii_255 else None

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

    def get_cell_size(self) -> tuple[int, int]:
        """
        Get the character cell dimensions (width, height) in pixels.

        Returns:
            Tuple of (char_width, char_height).
        """
        return self.cw, self.ch

    def set_color_mode(self, mode: str) -> None:
        """
        Set visual color palette / grading mode.

        Args:
            mode: 'truecolor', 'grayscale', 'green', 'amber', or 'cyberpunk'.
        """
        self.color_mode = mode.lower() if mode else "truecolor"

    @staticmethod
    def apply_color_mode(colors: np.ndarray, mode: str) -> np.ndarray:
        """
        Apply vintage color theme or monochrome grading to RGB matrix.

        Args:
            colors: 3D numpy array (rows, cols, 3) uint8 RGB colors.
            mode: Color grading style name.

        Returns:
            Processed 3D numpy array (rows, cols, 3) uint8 RGB colors.
        """
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
        screen: Surface,
        char_indices: np.ndarray,
        colors: np.ndarray,
        dest_rect: Rect | Sequence[int] | None = None,
    ) -> None:
        """
        Render a character matrix with Truecolor RGB onto the target screen.

        Args:
            screen: Destination Pygame surface.
            char_indices: 2D numpy array (rows, cols) of character ramp indices.
            colors: 3D numpy array (rows, cols, 3) or (rows, cols, 4) uint8 RGB colors.
            dest_rect: Optional destination Rect or (x, y, w, h) bounding box on screen.
        """
        if char_indices is None or colors is None:
            return

        rows, cols = char_indices.shape[:2]
        if cols <= 0 or rows <= 0:
            raise ValueError(
                "[HATA / ERROR] Grid boyutları pozitif olmalıdır / Grid dimensions must be positive"
            )

        w = cols * self.cw
        h = rows * self.ch

        # Update cached grid positions and mask surface if dimensions change
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

        # 1. Build mask from cached white glyphs
        mask_surf = self._cached_mask
        mask_surf.fill((0, 0, 0))

        flat = char_indices.ravel()
        if np.issubdtype(char_indices.dtype, np.integer):
            min_val = int(np.min(flat)) if flat.size > 0 else 0
            max_val = int(np.max(flat)) if flat.size > 0 else 0
            if 0 <= min_val and max_val < len(self.ramp_glyphs) and self._cached_ramp_stack_2d is not None:
                grid_glyphs = self._cached_ramp_stack_2d[char_indices]
                grid_arr = grid_glyphs.transpose(1, 2, 0, 3).reshape(w, h)
                pygame.surfarray.blit_array(mask_surf, grid_arr)
            elif 0 <= min_val and max_val < len(self.ascii_glyphs) and self._cached_ascii_stack_2d is not None:
                grid_glyphs = self._cached_ascii_stack_2d[char_indices]
                grid_arr = grid_glyphs.transpose(1, 2, 0, 3).reshape(w, h)
                pygame.surfarray.blit_array(mask_surf, grid_arr)
            else:
                flat_list = flat.tolist()
                space_surf = self.glyphs[" "]
                if max_val < len(self.ramp_glyphs):
                    lut = self.ramp_glyphs
                    blit_list = [
                        (lut[idx] if 0 <= idx < len(lut) else space_surf, pos)
                        for idx, pos in zip(flat_list, self._cached_positions)
                    ]
                else:
                    lut = self.ascii_glyphs
                    blit_list = [
                        (lut[idx] if 0 <= idx < len(lut) else space_surf, pos)
                        for idx, pos in zip(flat_list, self._cached_positions)
                    ]
                mask_surf.blits(blit_list, doreturn=False)
        else:
            space_surf = self.glyphs[" "]
            blit_list = [
                (self.glyphs.get(str(ch), space_surf), pos)
                for ch, pos in zip(flat.tolist(), self._cached_positions)
            ]
            mask_surf.blits(blit_list, doreturn=False)

        # 2. Convert and scale Truecolor video frame
        if self.color_mode and self.color_mode not in ("truecolor", "rgb", "color"):
            colors = self.apply_color_mode(colors, self.color_mode)

        if colors.ndim == 3 and colors.shape[2] == 4:
            colors = colors[..., :3]

        if not colors.flags.c_contiguous:
            colors = np.ascontiguousarray(colors)

        color_surf = pygame.image.frombuffer(colors.data, (cols, rows), "RGB")
        scaled_color = pygame.transform.scale(color_surf, (w, h))

        # 3. Multiply mask with Truecolor canvas
        scaled_color.blit(mask_surf, (0, 0), special_flags=pygame.BLEND_MULT)

        # 4. Blit composited canvas to target screen with 1:1 native sharpness
        if dest_rect is None:
            screen.blit(scaled_color, (0, 0))
        else:
            dx, dy = dest_rect[0], dest_rect[1]
            if len(dest_rect) >= 4:
                dw, dh = dest_rect[2], dest_rect[3]
                if w <= dw and h <= dh:
                    # Native 1:1 unscaled pixel blit: zero blur, vector crispness, centered
                    offset_x = dx + (dw - w) // 2
                    offset_y = dy + (dh - h) // 2
                    screen.blit(scaled_color, (offset_x, offset_y))
                elif dw > 0 and dh > 0:
                    # Content slightly larger than viewport: downscale to fit
                    scale = min(dw / w, dh / h)
                    fit_w = max(1, int(w * scale))
                    fit_h = max(1, int(h * scale))
                    offset_x = dx + (dw - fit_w) // 2
                    offset_y = dy + (dh - fit_h) // 2
                    fitted_surf = pygame.transform.scale(scaled_color, (fit_w, fit_h))
                    screen.blit(fitted_surf, (offset_x, offset_y))
                else:
                    screen.blit(scaled_color, (dx, dy))
            else:
                screen.blit(scaled_color, (dx, dy))

    def render_to_rgb_array(
        self,
        char_indices: np.ndarray,
        colors: np.ndarray,
        color_mode: str | None = None,
        target_shape: tuple[int, int] | None = None,
    ) -> np.ndarray:
        """
        Directly rasterize ASCII character indices and colors into an RGB ndarray.

        Args:
            char_indices: 2D numpy array (rows, cols) of character ramp indices.
            colors: 3D numpy array (rows, cols, 3) uint8 RGB colors.
            color_mode: Optional color grading mode override.
            target_shape: Optional (target_h, target_w) canvas dimensions for padding.

        Returns:
            RGB uint8 numpy array with exact pixel visual fidelity.
        """
        if char_indices is None or colors is None:
            if target_shape is not None:
                return np.zeros((target_shape[0], target_shape[1], 3), dtype=np.uint8)
            return np.zeros((0, 0, 3), dtype=np.uint8)

        rows, cols = char_indices.shape[:2]
        if cols <= 0 or rows <= 0:
            raise ValueError(
                "[HATA / ERROR] Grid boyutları pozitif olmalıdır / Grid dimensions must be positive"
            )

        if colors.shape[0] != rows or colors.shape[1] != cols:
            raise ValueError(
                f"[HATA / ERROR] Grid boyutları uyuşmuyor / Grid dimensions mismatch: "
                f"indices {char_indices.shape} vs colors {colors.shape}"
            )

        effective_mode = color_mode if color_mode is not None else self.color_mode
        if effective_mode and effective_mode not in ("truecolor", "rgb", "color"):
            colors = self.apply_color_mode(colors, effective_mode)

        if colors.ndim == 3 and colors.shape[2] == 4:
            colors = colors[..., :3]

        if not colors.flags.c_contiguous:
            colors = np.ascontiguousarray(colors)

        # Handle non-integer (string/object) character arrays
        if not np.issubdtype(char_indices.dtype, np.integer):
            try:
                char_arr = np.asarray(char_indices, dtype=str)
                char_indices = np.vectorize(
                    lambda x: ord(x[0]) if len(x) > 0 else 32, otypes=[np.int32]
                )(char_arr)
            except (ValueError, TypeError, IndexError):
                char_indices = np.full((rows, cols), 32, dtype=np.int32)

        flat = char_indices.ravel()
        min_val = int(np.min(flat)) if flat.size > 0 else 0
        max_val = int(np.max(flat)) if flat.size > 0 else 0

        # Choose 255-scaled glyph stack with blank fallback at index n_glyphs
        if max_val < len(self.ramp_glyphs) and self._cached_ramp_stack_255 is not None:
            stack = self._cached_ramp_stack_255
            n_glyphs = len(self.ramp_glyphs)
        elif self._cached_ascii_stack_255 is not None:
            stack = self._cached_ascii_stack_255
            n_glyphs = len(self.ascii_glyphs)
        else:
            cs = pygame.Surface((cols * self.cw, rows * self.ch))
            self.render_frame(cs, char_indices, colors)
            buf = pygame.image.tobytes(cs, "RGB")
            return np.frombuffer(buf, dtype=np.uint8).reshape(
                (rows * self.ch, cols * self.cw, 3)
            )

        # Map negative and out-of-range indices safely to the blank glyph (at index n_glyphs)
        if min_val >= 0 and max_val < n_glyphs:
            safe_indices = char_indices
        else:
            safe_indices = np.where(
                (char_indices >= 0) & (char_indices < n_glyphs), char_indices, n_glyphs
            )

        m_2d = stack[safe_indices].swapaxes(1, 2).reshape(rows * self.ch, cols * self.cw)
        c_scaled = cv2.resize(
            colors,
            (cols * self.cw, rows * self.ch),
            interpolation=cv2.INTER_NEAREST,
        )
        rgb_frame = cv2.bitwise_and(c_scaled, c_scaled, mask=m_2d)

        if target_shape is not None:
            th, tw = target_shape
            cur_h, cur_w = rows * self.ch, cols * self.cw
            if th != cur_h or tw != cur_w:
                if cur_h <= th and cur_w <= tw:
                    canvas = np.zeros((th, tw, 3), dtype=np.uint8)
                    off_y = (th - cur_h) // 2
                    off_x = (tw - cur_w) // 2
                    canvas[off_y : off_y + cur_h, off_x : off_x + cur_w] = rgb_frame
                    return canvas
                else:
                    scale = min(tw / max(1, cur_w), th / max(1, cur_h))
                    dw = max(1, int(cur_w * scale))
                    dh = max(1, int(cur_h * scale))
                    scaled = cv2.resize(rgb_frame, (dw, dh), interpolation=cv2.INTER_AREA)
                    canvas = np.zeros((th, tw, 3), dtype=np.uint8)
                    off_y = (th - dh) // 2
                    off_x = (tw - dw) // 2
                    canvas[off_y : off_y + dh, off_x : off_x + dw] = scaled
                    return canvas

        return rgb_frame

    def render_to_yuv_array(
        self,
        char_indices: np.ndarray,
        colors: np.ndarray,
        color_mode: str | None = None,
        target_shape: tuple[int, int] | None = None,
    ) -> np.ndarray:
        """
        Rasterize character indices and colors into a YUV420p (I420) array.
        """
        rgb_arr = self.render_to_rgb_array(
            char_indices=char_indices,
            colors=colors,
            color_mode=color_mode,
            target_shape=target_shape,
        )
        return cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2YUV_I420)

