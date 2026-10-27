"""Scanline, vignette, and bloom effects for ASCII frames."""

from __future__ import annotations

from typing import TYPE_CHECKING

import cv2
import numpy as np
import pygame

if TYPE_CHECKING:
    from pygame import Surface


class CrtEffect:
    """
    Apply bloom, scanlines, and vignette using cached masks.
    """

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        """
        Initialize CRT shader overlays for specified dimensions.

        Args:
            width: Target window/surface width in pixels.
            height: Target window/surface height in pixels.
        """
        self.width = max(1, width)
        self.height = max(1, height)
        self.frame_count: int = 0
        self.rolling_offset: int = 0

        self.scanlines_surf: Surface | None = None
        self.vignette_surf: Surface | None = None
        self._cached_multiplier: np.ndarray | None = None

        self.resize(self.width, self.height)

    def resize(self, width: int, height: int) -> None:
        """
        Regenerate pre-rendered scanline and vignette surfaces on window resize.

        Args:
            width: New window width.
            height: New window height.
        """
        self.width = max(1, width)
        self.height = max(1, height)

        # 1. Pre-render scanlines alpha surface (alternating horizontal line dimming)
        scanlines = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        # Even rows have alpha 60, odd rows have alpha 0
        for y in range(0, self.height, 2):
            scanlines.fill((0, 0, 0, 60), rect=pygame.Rect(0, y, self.width, 1))
        self.scanlines_surf = scanlines

        # 2. Pre-render radial vignette surface (screen edge curvature darkening)
        low_w = max(4, min(160, self.width))
        low_h = max(4, min(90, self.height))

        xs = np.linspace(-1.0, 1.0, low_w, dtype=np.float32)
        ys = np.linspace(-1.0, 1.0, low_h, dtype=np.float32)
        xg, yg = np.meshgrid(xs, ys)
        dist_sq = xg**2 + yg**2

        # Radial curve: transparent in center, darkens smoothly toward corners
        alpha = np.clip((dist_sq - 0.4) / 0.8 * 140.0, 0, 140).astype(np.uint8)
        low_surf = pygame.Surface((low_w, low_h), pygame.SRCALPHA)
        low_surf.fill((0, 0, 0, 0))
        alpha_t = np.transpose(alpha, (1, 0))
        alpha_view = pygame.surfarray.pixels_alpha(low_surf)
        alpha_view[:] = alpha_t
        del alpha_view, alpha_t

        self.vignette_surf = pygame.transform.smoothscale(low_surf, (self.width, self.height))

        # 3. Precompute combined CRT scanlines + vignette multiplier for SIMD array rasterization
        comp = pygame.Surface((self.width, self.height))
        comp.fill((255, 255, 255))
        if self.scanlines_surf is not None:
            comp.blit(self.scanlines_surf, (0, 0))
        if self.vignette_surf is not None:
            comp.blit(self.vignette_surf, (0, 0))
        self._cached_multiplier = pygame.surfarray.array3d(comp).swapaxes(0, 1)

    def apply_to_rgb_array(self, rgb_arr: np.ndarray, crt_enabled: bool = True) -> np.ndarray:
        """
        Apply cached scanline and vignette masks to an RGB array.
        """
        if not crt_enabled:
            return rgb_arr

        h, w = rgb_arr.shape[:2]
        if w != self.width or h != self.height or self._cached_multiplier is None:
            self.resize(w, h)

        if self._cached_multiplier is None:
            return rgb_arr

        return cv2.multiply(rgb_arr, self._cached_multiplier, scale=1.0 / 255.0)

    def apply(self, screen: Surface, crt_enabled: bool = True, bloom: bool = False) -> None:
        """
        Apply CRT post-processing effects onto the screen surface in-place.

        Args:
            screen: Pygame display/canvas surface.
            crt_enabled: Whether retro CRT effects are active.
            bloom: Whether bloom is active (default False).
        """
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
        self.frame_count = (self.frame_count + 1) % 1000
        self.rolling_offset = self.frame_count % 4

        if self.scanlines_surf is not None:
            screen.blit(self.scanlines_surf, (0, 0))

        # 3. Radial vignette overlay
        if self.vignette_surf is not None:
            screen.blit(self.vignette_surf, (0, 0))
