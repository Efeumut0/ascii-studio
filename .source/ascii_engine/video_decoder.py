"""Decode video frames into ASCII indices and RGB arrays."""

from __future__ import annotations

import logging
import math
import os
from collections.abc import Generator
from dataclasses import dataclass
from typing import Self

import av
import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VideoMetadata:
    """Metadata container for probed video file properties."""

    duration: float
    fps: float
    width: int
    height: int
    total_frames: int
    has_audio: bool
    codec: str
    aspect_ratio: float


class VideoDecoder:
    """
    Decode with PyAV, resize to the character grid, and map luminance to ASCII.
    """

    def __init__(
        self,
        video_path: str,
        target_cols: int = 80,
        char_aspect: float = 0.55,
        char_ramp: str = " .:-=+*#%@",
    ) -> None:
        """
        Initialize the video decoder with path and grid parameters.

        Args:
            video_path: Path to the media file.
            target_cols: Number of horizontal ASCII character columns.
            char_aspect: Ratio of character font width to font height (~0.5 - 0.57).
            char_ramp: ASCII characters sorted from lowest luminance (dark) to highest (bright).

        Raises:
            FileNotFoundError: If the video file does not exist.
            ValueError: If the file is not a valid video or parameters are invalid.
        """
        if not os.path.isfile(video_path):
            raise FileNotFoundError(
                f"[HATA / ERROR] Video dosyası bulunamadı / Video file not found: {video_path}"
            )

        if target_cols <= 0:
            raise ValueError(
                f"[HATA / ERROR] Sütun sayısı pozitif olmalıdır / target_cols must be > 0: {target_cols}"
            )
        if char_aspect <= 0:
            raise ValueError(
                f"[HATA / ERROR] Karakter en/boy oranı pozitif olmalıdır / char_aspect must be > 0: {char_aspect}"
            )
        if not char_ramp:
            raise ValueError(
                "[HATA / ERROR] Karakter dizisi boş olamaz / char_ramp cannot be empty"
            )
        if len(char_ramp) > 256:
            raise ValueError("[HATA / ERROR] char_ramp must contain at most 256 characters")

        self.video_path = os.path.abspath(video_path)
        self.target_cols = target_cols
        self.char_aspect = char_aspect
        self.char_ramp = char_ramp

        try:
            self.container = av.open(self.video_path)
        except Exception as exc:
            raise ValueError(
                f"[HATA / ERROR] Video dosyası açılamadı / Failed to open video file: {video_path} ({exc})"
            ) from exc

        if not self.container.streams.video:
            self.container.close()
            raise ValueError(
                f"[HATA / ERROR] Dosyada geçerli bir video akışı bulunamadı / No valid video stream found in file: {video_path}"
            )

        self.video_stream = self.container.streams.video[0]
        # Multi-threaded H.264 decoding
        self.video_stream.thread_type = "AUTO"
        try:
            if hasattr(self.video_stream, "codec_context") and self.video_stream.codec_context:
                self.video_stream.codec_context.thread_type = "AUTO"
        except (AttributeError, av.FFmpegError, OSError) as err:
            logger.debug("Failed setting codec context thread_type: %s", err)

        # Extract metadata
        self.metadata = self._extract_metadata()

        # Aspect ratio correction formula: rows = round(target_cols * (height / width) * char_aspect)
        self.cols = int(self.target_cols)
        h_over_w = (self.metadata.height / self.metadata.width) if self.metadata.width > 0 else 1.0
        self.rows = max(1, round(self.cols * h_over_w * self.char_aspect))

        # Vectorized integer luminance weights: (77 * R + 150 * G + 29 * B) >> 8
        self._luminance_weights = np.array([77, 150, 29], dtype=np.uint32)

        # Precompute vectorized character ramp indexing LUT (0..255 -> uint8 index)
        ramp_len = len(self.char_ramp)
        self._ramp_lut = np.array(
            [min(ramp_len - 1, (i * ramp_len) >> 8) for i in range(256)],
            dtype=np.uint8,
        )

        self._last_pts = 0.0
        self._pending_frame: av.VideoFrame | None = None
        self._at_eof = False
        self._is_closed = False

    def _extract_metadata(self) -> VideoMetadata:
        """Probe stream and container properties to build VideoMetadata."""
        vs = self.video_stream

        # Duration calculation
        duration = 0.0
        if vs.duration is not None and vs.duration > 0 and vs.time_base is not None:
            duration = float(vs.duration * vs.time_base)
        elif self.container.duration is not None and self.container.duration > 0:
            duration = float(self.container.duration / 1e6)

        # FPS calculation
        fps = 30.0
        if vs.average_rate is not None and vs.average_rate > 0:
            fps = float(vs.average_rate)
        elif vs.guessed_rate is not None and vs.guessed_rate > 0:
            fps = float(vs.guessed_rate)

        width = int(vs.width) if vs.width else 0
        height = int(vs.height) if vs.height else 0

        # Frame count calculation
        if vs.frames is not None and vs.frames > 0:
            total_frames = int(vs.frames)
        elif duration > 0 and fps > 0:
            total_frames = round(duration * fps)
        else:
            total_frames = 0

        has_audio = len(self.container.streams.audio) > 0
        codec = vs.codec_context.name if (vs.codec_context and vs.codec_context.name) else "unknown"
        aspect_ratio = (width / height) if height > 0 else 1.0

        return VideoMetadata(
            duration=duration,
            fps=fps,
            width=width,
            height=height,
            total_frames=total_frames,
            has_audio=has_audio,
            codec=codec,
            aspect_ratio=aspect_ratio,
        )

    def get_metadata(self) -> VideoMetadata:
        """Return probed video metadata."""
        return self.metadata

    def _process_frame(self, frame: av.VideoFrame) -> tuple[float, np.ndarray, np.ndarray]:
        """
        Process a single av.VideoFrame into ASCII indices and RGB colors.

        Returns:
            Tuple of (pts_seconds, char_indices_uint8, rgb_colors_uint8).
        """
        if frame.pts is not None and frame.time_base is not None:
            pts_seconds = float(frame.pts * frame.time_base)
        else:
            frame_step = (1.0 / self.metadata.fps) if self.metadata.fps > 0 else 0.033333
            pts_seconds = self._last_pts + frame_step
        self._last_pts = pts_seconds

        # Fast conversion to RGB24 ndarray
        rgb = frame.to_ndarray(format="rgb24")

        # High-speed resizing using OpenCV INTER_LINEAR
        resized_rgb = cv2.resize(
            rgb,
            (self.cols, self.rows),
            interpolation=cv2.INTER_LINEAR,
        )

        # Integer-vectorized luminance calculation: (77 * R + 150 * G + 29 * B) >> 8
        luminance = ((resized_rgb.astype(np.uint32) @ self._luminance_weights) >> 8).astype(np.uint8)

        # Vectorized character ramp indexing
        char_indices = self._ramp_lut[luminance]

        return pts_seconds, char_indices, resized_rgb

    def iter_frames(self) -> Generator[tuple[float, np.ndarray, np.ndarray], None, None]:
        """
        Yield processed frames sequentially.

        Yields:
            (pts_seconds, char_indices_uint8, rgb_colors_uint8):
                pts_seconds: Presentation timestamp in seconds (float).
                char_indices_uint8: 2D ndarray of uint8 indices into char_ramp (shape: rows, cols).
                rgb_colors_uint8: 3D ndarray of uint8 RGB values (shape: rows, cols, 3).
        """
        if self._is_closed:
            raise RuntimeError(
                "[HATA / ERROR] Video çözücü kapatılmış / Video decoder is closed"
            )

        if self._at_eof and self._pending_frame is None:
            self.seek(0.0)
            self._at_eof = False

        if self._pending_frame is not None:
            frame = self._pending_frame
            self._pending_frame = None
            yield self._process_frame(frame)

        try:
            for frame in self.container.decode(self.video_stream):
                if self._is_closed:
                    break
                if self._pending_frame is not None:
                    pending = self._pending_frame
                    self._pending_frame = None
                    yield self._process_frame(pending)
                    if self._is_closed:
                        break
                yield self._process_frame(frame)
        except (av.error.EOFError, av.FFmpegError, OSError):
            pass

        if self._pending_frame is not None:
            pending = self._pending_frame
            self._pending_frame = None
            yield self._process_frame(pending)

        self._at_eof = True

    def iter_frames_at_fps(self, fps: float) -> Generator[tuple[float, np.ndarray, np.ndarray], None, None]:
        """Sample decoded frames on a constant-rate timeline without changing playback speed."""
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("[HATA / ERROR] FPS must be finite and greater than zero")

        previous_frame = None
        frame_number = 0
        origin = None
        for timestamp, char_indices, colors in self.iter_frames():
            if origin is None:
                origin = timestamp
            timestamp -= origin
            if previous_frame is not None:
                while frame_number / fps < timestamp - 1e-9:
                    yield frame_number / fps, previous_frame[0], previous_frame[1]
                    frame_number += 1
            previous_frame = (char_indices, colors)

        if previous_frame is not None:
            end_time = self.metadata.duration
            if end_time <= 0:
                end_time = timestamp + 1.0 / self.metadata.fps
            while frame_number / fps < end_time - 1e-9:
                yield frame_number / fps, previous_frame[0], previous_frame[1]
                frame_number += 1

    def seek(self, seconds: float) -> bool:
        """
        Seek PyAV container to target time and resume decoding.

        Args:
            seconds: Target timestamp in seconds.

        Returns:
            True if seek succeeded, False otherwise.
        """
        if self._is_closed:
            return False

        target_seconds = max(0.0, min(self.metadata.duration, float(seconds)))
        self._pending_frame = None

        if self.video_stream.time_base is not None and float(self.video_stream.time_base) > 0:
            target_pts = int(target_seconds / float(self.video_stream.time_base))
        else:
            target_pts = int(target_seconds * 1000)

        try:
            self.container.seek(target_pts, stream=self.video_stream, backward=True)
            self._last_pts = target_seconds

            # Forward-decode to exact target timestamp
            if target_seconds > 0.0:
                last_frame = None
                found = False
                try:
                    for frame in self.container.decode(self.video_stream):
                        last_frame = frame
                        pts = (
                            float(frame.pts * frame.time_base)
                            if (frame.pts is not None and frame.time_base is not None)
                            else target_seconds
                        )
                        if pts >= target_seconds:
                            self._pending_frame = frame
                            found = True
                            break
                    if not found and last_frame is not None:
                        self._pending_frame = last_frame
                        self._at_eof = True
                    else:
                        self._at_eof = False
                except (av.error.EOFError, av.FFmpegError, OSError):
                    if last_frame is not None:
                        self._pending_frame = last_frame
                    self._at_eof = True
            else:
                self._at_eof = False

            return True
        except (av.FFmpegError, OSError) as err:
            logger.warning("Video seek failed for target %s: %s", target_seconds, err)
            return False

    def close(self) -> None:
        """Cleanly close PyAV container and decoder resources."""
        if not self._is_closed:
            self._is_closed = True
            try:
                self.container.close()
            except (av.FFmpegError, OSError) as err:
                logger.debug("Error while closing container: %s", err)
            self._pending_frame = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()
