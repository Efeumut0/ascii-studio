#!/usr/bin/env python3
"""Render video as colored ASCII in an MP4 file."""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import queue
import re
import sys
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction

import av
import cv2
import numpy as np

# Ensure headless drivers when invoked from CLI or background workers
if "--headless" in sys.argv or os.environ.get("SDL_VIDEODRIVER") == "dummy":
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame

from ascii_engine.video_decoder import VideoDecoder
from ascii_ui.crt_effects import CrtEffect
from ascii_ui.renderer import (
    CLASSIC_16_RAMP,
    DEFAULT_RAMP,
    DETAILED_RAMP,
    EXTENDED_92_RAMP,
    AsciiRenderer,
)

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = "output"

RENDER_RESOLUTIONS: list[dict] = [
    {
        "id": "auto",
        "name": "Otomatik (Auto 1080p / 2K)",
        "tag": "AUTO",
        "desc": "Video özelliklerine göre 1080p veya 2K",
    },
    {
        "id": "1080p",
        "name": "1080p Full HD (1920x1080)",
        "tag": "1080p",
        "desc": "1920x1080 MP4",
    },
    {
        "id": "2k",
        "name": "2K Quad HD (2560x1440)",
        "tag": "2K",
        "desc": "2560x1440 MP4",
    },
    {
        "id": "4k",
        "name": "4K Ultra HD (3840x2160)",
        "tag": "4K",
        "desc": "3840x2160 MP4",
    },
    {
        "id": "720p",
        "name": "720p HD (1280x720)",
        "tag": "720p",
        "desc": "1280x720 MP4",
    },
    {
        "id": "original",
        "name": "Orijinal (1:1 Grid Boyutu)",
        "tag": "1:1",
        "desc": "Karakter ızgarasının piksel boyutu",
    },
]


def sanitize_video_folder_name(video_path: str) -> str:
    """Sanitize video filename into clean folder name for output/<video_name>/."""
    base = os.path.basename(video_path)
    stem, _ = os.path.splitext(base)
    tr_map = str.maketrans({
        "ç": "c", "Ç": "C",
        "ğ": "g", "Ğ": "G",
        "ı": "i", "I": "I", "İ": "I",
        "ö": "o", "Ö": "O",
        "ş": "s", "Ş": "S",
        "ü": "u", "Ü": "U",
    })
    safe = stem.translate(tr_map)
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", safe).strip("_")
    return safe if safe else "video_output"


def get_video_output_dir(video_path: str, base_dir: str = "output") -> str:
    """Return absolute path to output/<sanitized_video_name>/."""
    subfolder = sanitize_video_folder_name(video_path)
    return os.path.abspath(os.path.join(base_dir, subfolder))


# Quality presets
RENDER_PRESETS: dict[str, dict] = {
    "1": {
        "id": "low",
        "alias": "arcade",
        "cols": 50,
        "font_size": 14,
        "chars": DEFAULT_RAMP,
        "name": "1. LOW",
    },
    "2": {
        "id": "retro",
        "alias": "retro",
        "cols": 65,
        "font_size": 13,
        "chars": DEFAULT_RAMP,
        "name": "2. RETRO",
    },
    "3": {
        "id": "balanced",
        "alias": "terminal",
        "cols": 80,
        "font_size": 12,
        "chars": CLASSIC_16_RAMP,
        "name": "3. BALANCED",
    },
    "4": {
        "id": "classic",
        "alias": "classic",
        "cols": 95,
        "font_size": 11,
        "chars": CLASSIC_16_RAMP,
        "name": "4. CLASSIC",
    },
    "5": {
        "id": "high",
        "alias": "high",
        "cols": 110,
        "font_size": 10,
        "chars": DETAILED_RAMP,
        "name": "5. HIGH",
    },
    "6": {
        "id": "super",
        "alias": "super",
        "cols": 125,
        "font_size": 9,
        "chars": DETAILED_RAMP,
        "name": "6. SUPER",
    },
    "7": {
        "id": "ultra",
        "alias": "ultra",
        "cols": 140,
        "font_size": 8,
        "chars": DETAILED_RAMP,
        "name": "7. ULTRA",
    },
    "8": {
        "id": "master",
        "alias": "master",
        "cols": 160,
        "font_size": 8,
        "chars": DETAILED_RAMP,
        "name": "8. MASTER",
    },
    "9": {
        "id": "cinema",
        "alias": "cinema",
        "cols": 180,
        "font_size": 7,
        "chars": DETAILED_RAMP,
        "name": "9. CINEMA",
    },
    "10": {
        "id": "titan",
        "alias": "titan",
        "cols": 200,
        "font_size": 6,
        "chars": DETAILED_RAMP,
        "name": "10. TITAN",
    },
    "11": {
        "id": "overkill",
        "alias": "overkill",
        "cols": 230,
        "font_size": 6,
        "chars": DETAILED_RAMP,
        "name": "11. OVERKILL",
    },
    "12": {
        "id": "godlike",
        "alias": "godlike",
        "cols": 260,
        "font_size": 5,
        "chars": EXTENDED_92_RAMP,
        "name": "12. GODLIKE",
    },
    "13": {
        "id": "monolith",
        "alias": "monolith",
        "cols": 300,
        "font_size": 5,
        "chars": EXTENDED_92_RAMP,
        "name": "13. MONOLITH",
    },
    "14": {
        "id": "singularity",
        "alias": "singularity",
        "cols": 340,
        "font_size": 4,
        "chars": EXTENDED_92_RAMP,
        "name": "14. SINGULARITY",
    },
    "15": {
        "id": "infinite",
        "alias": "infinite",
        "cols": 380,
        "font_size": 4,
        "chars": EXTENDED_92_RAMP,
        "name": "15. INFINITE",
    },
}

# Lookup map by ID or alias
PRESET_LOOKUP: dict[str, dict] = {}
for key, p in RENDER_PRESETS.items():
    PRESET_LOOKUP[key] = p
    PRESET_LOOKUP[p["id"]] = p
    PRESET_LOOKUP[p["alias"]] = p
PRESET_LOOKUP["standard"] = RENDER_PRESETS["3"]


def resolve_preset_config(preset: str | int | None) -> dict:
    """Resolve quality preset configuration dict by id, number, or alias."""
    if preset is None:
        return RENDER_PRESETS["3"]
    p_key = str(preset).strip().lower()
    return PRESET_LOOKUP.get(p_key, RENDER_PRESETS["3"])


def compute_optimal_render_font_size(
    target_w: int,
    target_h: int,
    cols: int,
    rows: int,
    font_name: str = "consolas",
) -> int:
    """Find largest font size such that cols * cw <= target_w and rows * ch <= target_h."""
    if not pygame.font.get_init():
        pygame.font.init()
    best_fs = 2
    for fs in range(200, 2, -1):
        f = pygame.font.SysFont(font_name, fs)
        cw, ch = f.size("M")
        if cols * cw <= target_w and rows * ch <= target_h:
            return fs
    return best_fs


def resolve_render_resolution(
    resolution: str | None,
    cols: int,
    rows: int,
    base_font_size: int,
    duration: float,
    video_aspect: float | None = None,
    font_name: str = "consolas",
) -> tuple[int | None, int | None, int]:
    """
    Resolve target MP4 canvas dimensions (target_w, target_h) and optimal font size.

    Returns:
        Tuple of (target_w, target_h, optimal_font_size).
        If target_w or target_h is None, native grid dimensions (cols * cw, rows * ch) are used.
    """
    if not pygame.font.get_init():
        pygame.font.init()
    res_str = str(resolution or "auto").strip().lower()
    if res_str in ("original", "native", "1:1", "none"):
        return None, None, base_font_size

    if video_aspect is None or video_aspect <= 0:
        video_aspect = (cols * 0.55) / max(1, rows)

    if res_str == "auto":
        base_f = pygame.font.SysFont(font_name, base_font_size)
        bcw, bch = base_f.size("M")
        raw_w = cols * bcw
        raw_h = rows * bch

        # Low resolution -> upscale to 1080p
        # If already 1080p+, can upgrade to 2K (if short video duration <= 180s for render speed)
        if raw_h < 1080 and raw_w < 1920:
            target_tier = "1080p"
        elif duration <= 180.0:
            target_tier = "2k"
        else:
            target_tier = "1080p"
    else:
        target_tier = res_str

    target_w: int
    target_h: int

    m = re.match(r"^(\d+)\s*[xX*]\s*(\d+)$", target_tier)
    if m:
        target_w = int(m.group(1))
        target_h = int(m.group(2))
    elif target_tier in ("1080p", "fhd", "1080"):
        if video_aspect >= 1.0:
            target_h = 1080
            target_w = 1920 if abs(video_aspect - 16 / 9) < 0.1 else round(target_h * video_aspect)
        else:
            target_w = 1080
            target_h = 1920 if abs(video_aspect - 9 / 16) < 0.1 else round(target_w / video_aspect)
    elif target_tier in ("2k", "1440p", "qhd", "1440"):
        if video_aspect >= 1.0:
            target_h = 1440
            target_w = 2560 if abs(video_aspect - 16 / 9) < 0.1 else round(target_h * video_aspect)
        else:
            target_w = 1440
            target_h = 2560 if abs(video_aspect - 9 / 16) < 0.1 else round(target_w / video_aspect)
    elif target_tier in ("720p", "hd", "720"):
        if video_aspect >= 1.0:
            target_h = 720
            target_w = 1280 if abs(video_aspect - 16 / 9) < 0.1 else round(target_h * video_aspect)
        else:
            target_w = 720
            target_h = 1280 if abs(video_aspect - 9 / 16) < 0.1 else round(target_w / video_aspect)
    elif target_tier in ("4k", "2160p", "uhd", "2160"):
        if video_aspect >= 1.0:
            target_h = 2160
            target_w = 3840 if abs(video_aspect - 16 / 9) < 0.1 else round(target_h * video_aspect)
        else:
            target_w = 2160
            target_h = 3840 if abs(video_aspect - 9 / 16) < 0.1 else round(target_w / video_aspect)
    else:
        if video_aspect >= 1.0:
            target_h = 1080
            target_w = 1920
        else:
            target_w = 1080
            target_h = 1920

    target_w = max(2, (target_w + 1) // 2 * 2)
    target_h = max(2, (target_h + 1) // 2 * 2)

    optimal_fs = compute_optimal_render_font_size(target_w, target_h, cols, rows, font_name)
    return target_w, target_h, optimal_fs


def render_video_to_mp4(
    video_path: str,
    output_path: str | None = None,
    preset: str | None = None,
    cols: int | None = None,
    fps: float | None = None,
    chars: str | None = None,
    font_size: int | None = None,
    crt: bool = False,
    audio: bool = True,
    color_mode: str = "truecolor",
    char_aspect: float = 0.55,
    overwrite: bool = True,
    progress_callback: Callable[[int, int, float, float], None] | None = None,
    encoder_preset: str = "veryfast",
    workers: int | None = None,
    resolution: str = "auto",
    crf: int = 20,
) -> str:
    """
    Render input video into a standalone MP4 video with ASCII character art visual frames.

    Args:
        video_path: Path to source video file.
        output_path: Target MP4 path (defaults to output_rendered/<name>_ascii.mp4).
        preset: Optional quality preset (1..15 or low..infinite).
        cols: Target columns (overrides preset if set).
        fps: Target framerate (defaults to source video FPS).
        chars: Character luminance ramp string.
        font_size: Monospace font point size.
        crt: Whether CRT scanlines & vignette are applied.
        audio: Whether audio stream is muxed into destination MP4.
        color_mode: Theme ('truecolor', 'grayscale', 'green', 'amber', 'cyberpunk').
        char_aspect: Font width to height aspect ratio.
        overwrite: Whether to overwrite existing destination MP4.
        progress_callback: Optional callback(current_frame, total_frames, fps, eta).
        encoder_preset: PyAV H.264 speed preset (default: 'veryfast').
        workers: Parallel frame rasterization worker thread count (default: auto).

    Returns:
        Absolute normalized path to the created MP4 video file.
    """
    if not video_path:
        raise ValueError("[HATA / ERROR] Video yolu boş olamaz / Video path cannot be empty")
    if fps is not None and (not math.isfinite(fps) or fps <= 0):
        raise ValueError("[HATA / ERROR] FPS must be finite and greater than zero")
    if not isinstance(crf, int) or not 0 <= crf <= 51:
        raise ValueError("[HATA / ERROR] CRF must be an integer between 0 and 51")

    resolved_video = os.path.abspath(video_path)
    if not os.path.exists(resolved_video):
        raise FileNotFoundError(
            f"[HATA / ERROR] Video dosyası bulunamadı / Video file not found: {video_path}"
        )

    if os.path.getsize(resolved_video) == 0:
        raise ValueError(
            f"[HATA / ERROR] Video dosyası boş (0 bayt) / Video file is empty: {video_path}"
        )

    # Resolve preset defaults
    cfg = resolve_preset_config(preset)
    final_cols = int(cols) if cols is not None and cols > 0 else cfg["cols"]
    final_font_size = int(font_size) if font_size is not None and font_size > 0 else cfg["font_size"]
    final_chars = chars if chars else cfg["chars"]
    final_color_mode = color_mode if color_mode else "truecolor"

    # Resolve output path
    if output_path is None:
        folder_dir = get_video_output_dir(resolved_video, DEFAULT_OUTPUT_DIR)
        os.makedirs(folder_dir, exist_ok=True)
        sub_name = os.path.basename(folder_dir)
        dest_mp4 = os.path.abspath(os.path.join(folder_dir, f"{sub_name}_ascii.mp4"))
    else:
        dest_mp4 = os.path.abspath(output_path)
        out_dir = os.path.dirname(dest_mp4)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

    if os.path.exists(dest_mp4) and os.path.samefile(resolved_video, dest_mp4):
        raise ValueError("[HATA / ERROR] Input video and output file must be different")

    if os.path.exists(dest_mp4) and not overwrite:
        raise FileExistsError(
            f"[HATA / ERROR] Hedef dosya zaten mevcut / Destination file already exists: {dest_mp4}"
        )

    # 1. Initialize Pygame subsystems (headless)
    if os.environ.get("SDL_VIDEODRIVER") is None:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    if os.environ.get("SDL_AUDIODRIVER") is None:
        os.environ["SDL_AUDIODRIVER"] = "dummy"

    pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()

    # 2. Initialize Video Decoder
    decoder = VideoDecoder(
        video_path=resolved_video,
        target_cols=final_cols,
        char_aspect=char_aspect,
        char_ramp=final_chars,
    )

    metadata = decoder.get_metadata()
    actual_rows = decoder.rows
    actual_cols = decoder.cols
    target_fps = float(fps) if (fps is not None and fps > 0) else metadata.fps
    target_fps = max(1.0, min(60.0, target_fps))
    total_frames = math.ceil(metadata.duration * target_fps)
    total_frames = max(1, total_frames)

    # 3. Setup Monospace ASCII Renderer & Canvas Resolution
    src_w = metadata.width if metadata.width > 0 else 1920
    src_h = metadata.height if metadata.height > 0 else 1080
    v_aspect = (src_w / src_h) if src_h > 0 else ((actual_cols * char_aspect) / max(1, actual_rows))

    target_w, target_h, optimal_fs = resolve_render_resolution(
        resolution=resolution,
        cols=actual_cols,
        rows=actual_rows,
        base_font_size=final_font_size,
        duration=metadata.duration,
        video_aspect=v_aspect,
    )

    if font_size is None and target_w is not None and target_h is not None:
        effective_font_size = optimal_fs
    else:
        effective_font_size = final_font_size

    renderer = AsciiRenderer(
        font_size=effective_font_size,
        char_ramp=final_chars,
        color_mode=final_color_mode,
    )
    cw, ch = renderer.get_cell_size()

    # Enforce even pixel dimensions for H.264 yuv420p encoder compatibility
    if target_w is not None and target_h is not None:
        canvas_w = target_w
        canvas_h = target_h
    else:
        canvas_w = ((actual_cols * cw) + 1) // 2 * 2
        canvas_h = ((actual_rows * ch) + 1) // 2 * 2

    crt_effect: CrtEffect | None = None
    if crt:
        crt_effect = CrtEffect(canvas_w, canvas_h)

    # 4. Open PyAV output container
    out_container = av.open(dest_mp4, mode="w")
    v_stream = out_container.add_stream("libx264", rate=Fraction(str(target_fps)).limit_denominator(100000))
    v_stream.width = canvas_w
    v_stream.height = canvas_h
    v_stream.pix_fmt = "yuv420p"
    v_stream.options = {"preset": encoder_preset, "crf": str(crf), "threads": "auto"}

    # Setup Audio stream if audio enabled and source has audio
    in_audio_container: av.container.InputContainer | None = None
    a_stream: av.stream.Stream | None = None

    if audio and metadata.has_audio:
        try:
            in_audio_container = av.open(resolved_video)
            if in_audio_container.streams.audio:
                in_audio = in_audio_container.streams.audio[0]
                a_stream = out_container.add_stream("aac", rate=in_audio.rate)
                a_stream.layout = "stereo"
        except (av.FFmpegError, OSError, IndexError) as exc:
            logger.debug("Audio muxing skipped: %s", exc)
            if in_audio_container:
                in_audio_container.close()
                in_audio_container = None
            a_stream = None

    # 5. Multithreaded frame rendering & background encoding pipeline
    encode_queue: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=32)
    encode_error: Exception | None = None

    def encoder_worker() -> None:
        nonlocal encode_error
        try:
            while True:
                item = encode_queue.get()
                if item is None:
                    break
                v_frame = av.VideoFrame.from_ndarray(item, format="yuv420p")
                v_frame.pts = None
                for packet in v_stream.encode(v_frame):
                    out_container.mux(packet)
                encode_queue.task_done()
            for packet in v_stream.encode():
                out_container.mux(packet)
        except (av.FFmpegError, OSError, ValueError, RuntimeError) as exc:
            encode_error = exc

    enc_thread = threading.Thread(target=encoder_worker, daemon=True)
    enc_thread.start()

    max_workers = (
        workers
        if (workers is not None and workers > 0)
        else min(8, max(2, (os.cpu_count() or 4) - 1))
    )

    def rasterize_frame(char_indices: np.ndarray, rgb_colors: np.ndarray) -> np.ndarray:
        rgb_arr = renderer.render_to_rgb_array(
            char_indices=char_indices,
            colors=rgb_colors,
            color_mode=final_color_mode,
            target_shape=(canvas_h, canvas_w),
        )
        if crt_effect is not None:
            rgb_arr = crt_effect.apply_to_rgb_array(rgb_arr, crt_enabled=True)
        return cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2YUV_I420)

    def safe_put_frame(frame: np.ndarray) -> None:
        while True:
            if encode_error is not None:
                raise encode_error
            if not enc_thread.is_alive():
                raise RuntimeError("Encoder background thread terminated unexpectedly")
            try:
                encode_queue.put(frame, timeout=0.1)
                break
            except queue.Full:
                continue

    start_time = time.perf_counter()
    frame_idx = 0
    max_window = max_workers * 2

    try:
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                window: list = []
                for _pts, char_indices, rgb_colors in decoder.iter_frames_at_fps(target_fps):
                    if encode_error is not None:
                        raise encode_error

                    fut = pool.submit(rasterize_frame, char_indices, rgb_colors)
                    window.append(fut)

                    if len(window) >= max_window:
                        ready_frame = window.pop(0).result()
                        safe_put_frame(ready_frame)
                        frame_idx += 1
                        elapsed = time.perf_counter() - start_time
                        current_render_fps = frame_idx / elapsed if elapsed > 0 else 0.0
                        eta = (total_frames - frame_idx) / current_render_fps if current_render_fps > 0 else 0.0
                        if progress_callback:
                            progress_callback(frame_idx, total_frames, current_render_fps, eta)

                while window:
                    if encode_error is not None:
                        raise encode_error

                    ready_frame = window.pop(0).result()
                    safe_put_frame(ready_frame)
                    frame_idx += 1
                    elapsed = time.perf_counter() - start_time
                    current_render_fps = frame_idx / elapsed if elapsed > 0 else 0.0
                    eta = (total_frames - frame_idx) / current_render_fps if current_render_fps > 0 else 0.0
                    if progress_callback:
                        progress_callback(frame_idx, total_frames, current_render_fps, eta)

        finally:
            decoder.close()
            while enc_thread.is_alive():
                try:
                    encode_queue.put(None, timeout=0.1)
                    break
                except queue.Full:
                    continue
            enc_thread.join()

        if encode_error is not None:
            raise encode_error
        if frame_idx == 0:
            raise ValueError("[HATA / ERROR] No frames could be decoded from video")

        # 6. Encode Audio Stream (if active)
        if in_audio_container and a_stream:
            try:
                audio_source_stream = in_audio_container.streams.audio[0]
                for audio_frame in in_audio_container.decode(audio_source_stream):
                    audio_frame.pts = None
                    for packet in a_stream.encode(audio_frame):
                        out_container.mux(packet)
                for packet in a_stream.encode():
                    out_container.mux(packet)
            except (av.FFmpegError, OSError) as exc:
                logger.debug("Audio stream error while muxing: %s", exc)
            finally:
                in_audio_container.close()
                in_audio_container = None
    finally:
        if in_audio_container:
            try:
                in_audio_container.close()
            except (av.FFmpegError, OSError) as exc:
                logger.debug("Failed closing in_audio_container: %s", exc)
        # 7. Finalize and close output container
        out_container.close()

    total_time = time.perf_counter() - start_time
    logger.info("Render complete: %d frames in %.2fs (%.1f FPS) -> %s", frame_idx, total_time, frame_idx / max(0.001, total_time), dest_mp4)
    return dest_mp4


def create_parser() -> argparse.ArgumentParser:
    """CLI Argument parser for ascii_video_renderer."""
    parser = argparse.ArgumentParser(
        description="Render video to standalone MP4 video with ASCII typography and retro styling",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("video", nargs="?", default=None, help="Input video file path (positional)")
    parser.add_argument("-i", "--input", dest="input", default=None, help="Input video file path")
    parser.add_argument("-o", "--output", dest="output", default=None, help="Output MP4 file path")
    parser.add_argument(
        "--quality",
        "-q",
        default="balanced",
        help="Visual quality preset (1..15 or low, balanced, high, ultra, godlike, infinite...)",
    )
    parser.add_argument("--cols", "-w", type=int, default=None, help="Target character columns")
    parser.add_argument("--fps", type=float, default=None, help="Target output FPS")
    parser.add_argument("--chars", type=str, default=None, help="ASCII luminance character ramp")
    parser.add_argument(
        "--resolution",
        "-r",
        default="auto",
        help="Target render resolution (auto, 1080p, 2k/1440p, 720p, 4k, original/native, or WxH)",
    )
    parser.add_argument("--font-size", type=int, default=None, help="Font point size")
    parser.add_argument(
        "--crt",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Apply vintage CRT scanlines and vignette effect",
    )
    parser.add_argument(
        "--audio",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Mux audio stream into output video (use --no-audio for silent)",
    )
    parser.add_argument(
        "--color-mode",
        type=str,
        default="truecolor",
        help="Color grading style (truecolor, grayscale/siyah-beyaz, green/matrix, amber, cyberpunk)",
    )
    parser.add_argument(
        "--overwrite",
        "-f",
        action="store_true",
        default=True,
        help="Overwrite destination file if it exists",
    )
    parser.add_argument(
        "--gui-progress",
        action="store_true",
        default=False,
        help="Emit real-time JSON progress lines to stdout for GUI tracking",
    )
    parser.add_argument(
        "--encoder-preset",
        default="veryfast",
        choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium"],
        help="PyAV H.264 encoder speed preset (default: veryfast)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of parallel worker threads for frame rasterization (default: auto)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for video rendering."""
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    parser = create_parser()
    args = parser.parse_args(argv)

    input_file = args.input or args.video
    if not input_file:
        print("[HATA / ERROR] Lutfen bir video dosyasi belirtin! / Please specify a video file (-i <video>)", file=sys.stderr)
        return 1

    last_json_time = 0.0

    def cli_progress(cur: int, total: int, fps: float, eta: float) -> None:
        nonlocal last_json_time
        tot = max(1, max(cur, total))
        raw_pct = min(100.0, max(0.0, (cur / tot) * 100.0))
        # Video frames represent 0% to 95% of total render progress
        pct = raw_pct * 0.95
        bar_len = 20
        filled = int(bar_len * (pct / 100.0))
        bar = "█" * filled + "░" * (bar_len - filled)
        text = f"[{bar}] {pct:5.1f}% ({cur}/{tot}) | {fps:5.1f} FPS | ETA: {eta:4.1f}s"

        if getattr(args, "gui_progress", False):
            now = time.perf_counter()
            if now - last_json_time >= 0.033 or cur >= total:
                last_json_time = now
                payload = {
                    "type": "progress",
                    "pct": round(pct, 1),
                    "current": cur,
                    "total": tot,
                    "fps": round(fps, 1),
                    "eta": round(eta, 1),
                    "bar": bar,
                    "text": text,
                    "stage": f"Video Kareleri İşleniyor ({cur}/{tot})",
                }
                sys.stdout.write(f"\n__PROGRESS_JSON__{json.dumps(payload)}\n")
                sys.stdout.flush()
        else:
            bar_len_cli = 30
            filled_cli = round(bar_len_cli * (raw_pct / 100.0))
            bar_cli = "#" * filled_cli + "-" * (bar_len_cli - filled_cli)
            sys.stdout.write(f"\r[RENDER] [{bar_cli}] {raw_pct:5.1f}% ({cur}/{tot}) | {fps:5.1f} FPS | ETA: {eta:4.1f}s")
            sys.stdout.flush()

    if not getattr(args, "gui_progress", False):
        print(f"\n[RENDER] ASCII Video Render Baslatiliyor: {input_file}")
        print(f"   Kalite: {args.quality} | Ses: {args.audio} | CRT: {args.crt} | Renk: {args.color_mode}")

    try:
        out_path = render_video_to_mp4(
            video_path=input_file,
            output_path=args.output,
            preset=args.quality,
            cols=args.cols,
            fps=args.fps,
            chars=args.chars,
            font_size=args.font_size,
            crt=args.crt,
            audio=args.audio,
            color_mode=args.color_mode,
            overwrite=args.overwrite,
            progress_callback=cli_progress,
            encoder_preset=getattr(args, "encoder_preset", "veryfast"),
            workers=getattr(args, "workers", None),
            resolution=getattr(args, "resolution", "auto"),
        )
        if getattr(args, "gui_progress", False):
            p_done = {
                "type": "progress",
                "pct": 100.0,
                "current": 100,
                "total": 100,
                "fps": 0.0,
                "eta": 0.0,
                "bar": "█" * 20,
                "text": "[████████████████████] 100% | Render Tamamlandı!",
                "stage": f"[BAŞARILI] Video kaydedildi: {os.path.basename(out_path)}",
            }
            sys.stdout.write(f"\n__PROGRESS_JSON__{json.dumps(p_done)}\n")
            sys.stdout.write(f"\n__PROGRESS_JSON__{json.dumps({'type': 'done', 'success': True, 'output': out_path, 'folder': os.path.dirname(out_path)})}\n")
            sys.stdout.flush()
        else:
            print(f"\n\n[BASARILI] Video render tamamlandi: {out_path}")
            print(f"   Dosya Boyutu: {os.path.getsize(out_path) / (1024 * 1024):.2f} MB\n")
        return 0
    except (FileNotFoundError, ValueError, OSError, av.FFmpegError) as exc:
        if getattr(args, "gui_progress", False):
            sys.stdout.write(f"\n__PROGRESS_JSON__{json.dumps({'type': 'done', 'success': False, 'error': str(exc)})}\n")
            sys.stdout.flush()
        print(f"\n[HATA / ERROR] Render başarısız: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        if getattr(args, "gui_progress", False):
            sys.stdout.write(f"\n__PROGRESS_JSON__{json.dumps({'type': 'done', 'success': False, 'error': 'İptal edildi'})}\n")
            sys.stdout.flush()
        print("\n[İPTAL] Kullanıcı tarafından durduruldu.", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
