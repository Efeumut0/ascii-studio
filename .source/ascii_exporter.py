#!/usr/bin/env python3
"""Export ASCII frames, audio, configuration, and a standalone player."""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from collections.abc import Callable, Sequence

import av
import numpy as np

from ascii_engine.audio_engine import AudioEngine
from ascii_engine.video_decoder import VideoDecoder

logger = logging.getLogger(__name__)

from ascii_ui.renderer import (
    CLASSIC_16_RAMP,
    DEFAULT_RAMP,
    DETAILED_RAMP,
    EXTENDED_92_RAMP,
)

# Quality presets
QUALITY_PRESET_MAP: dict[str, dict] = {
    "1": {"id": "low", "cols": 50, "chars": DEFAULT_RAMP},
    "2": {"id": "retro", "cols": 65, "chars": DEFAULT_RAMP},
    "3": {"id": "balanced", "cols": 80, "chars": CLASSIC_16_RAMP},
    "4": {"id": "classic", "cols": 95, "chars": CLASSIC_16_RAMP},
    "5": {"id": "high", "cols": 110, "chars": DETAILED_RAMP},
    "6": {"id": "super", "cols": 125, "chars": DETAILED_RAMP},
    "7": {"id": "ultra", "cols": 140, "chars": DETAILED_RAMP},
    "8": {"id": "master", "cols": 160, "chars": DETAILED_RAMP},
    "9": {"id": "cinema", "cols": 180, "chars": DETAILED_RAMP},
    "10": {"id": "titan", "cols": 200, "chars": DETAILED_RAMP},
    "11": {"id": "overkill", "cols": 230, "chars": DETAILED_RAMP},
    "12": {"id": "godlike", "cols": 260, "chars": EXTENDED_92_RAMP},
    "13": {"id": "monolith", "cols": 300, "chars": EXTENDED_92_RAMP},
    "14": {"id": "singularity", "cols": 340, "chars": EXTENDED_92_RAMP},
    "15": {"id": "infinite", "cols": 380, "chars": EXTENDED_92_RAMP},
}

QUALITY_LOOKUP: dict[str, dict] = {}
for k, v in QUALITY_PRESET_MAP.items():
    QUALITY_LOOKUP[k] = v
    QUALITY_LOOKUP[v["id"]] = v
QUALITY_LOOKUP["standard"] = QUALITY_PRESET_MAP["3"]

DEFAULT_OUTPUT_DIR = None
DEFAULT_OUTPUT_ROOT = "output"

EXIT_SUCCESS = 0
EXIT_FILE_NOT_FOUND = 1
EXIT_FORMAT_ERROR = 2


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


def save_npz_fast(file_path: str, compress_level: int = 1, **arrays: np.ndarray) -> None:
    """
    Save arrays as a DEFLATE-compressed NPZ archive readable by np.load.
    """
    with zipfile.ZipFile(
        file_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=compress_level,
    ) as zf:
        for name, arr in arrays.items():
            with zf.open(f"{name}.npy", "w", force_zip64=True) as f:
                np.lib.format.write_array(f, np.ascontiguousarray(arr), allow_pickle=False)



def get_resource_path(relative_path: str) -> str:
    """
    Resolve asset path dynamically for development and PyInstaller bundles.

    Args:
        relative_path: Relative path to resource asset.

    Returns:
        Absolute normalized path to the target asset.
    """
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, relative_path)


class ExporterArgumentParser(argparse.ArgumentParser):
    """Custom ArgumentParser supporting both positional video and --input / -i."""

    def parse_args(
        self,
        args: Sequence[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> argparse.Namespace:
        parsed = super().parse_args(args=args, namespace=namespace)
        input_file = parsed.input or parsed.video
        if not input_file:
            self.error(
                "[HATA / ERROR] Girdi video dosyası belirtilmelidir / "
                "Input video path is required (positional or --input / -i)"
            )
        parsed.input = input_file
        if parsed.video is None:
            parsed.video = input_file
        return parsed


def create_parser() -> ExporterArgumentParser:
    """
    Create and configure CLI argument parser for the standalone ASCII exporter.

    Returns:
        Configured ExporterArgumentParser instance.
    """
    parser = ExporterArgumentParser(
        description="Export any video into a standalone portable retro ASCII player project",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Input video specification (supports positional or --input / -i)
    parser.add_argument(
        "video",
        nargs="?",
        default=None,
        help="Input video file path (positional)",
    )
    parser.add_argument(
        "--input",
        "-i",
        dest="input",
        default=None,
        help="Input video file path",
    )

    # Output destination
    parser.add_argument(
        "--output",
        "-o",
        dest="output",
        default=DEFAULT_OUTPUT_DIR,
        help="Destination directory for the standalone project bundle (defaults to output/<video_name>/)",
    )

    # Grid and rendering options
    parser.add_argument(
        "--cols",
        "-w",
        type=int,
        default=80,
        help="Target character columns (horizontal resolution, 20-450)",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=None,
        help="Target FPS cap (defaults to source video FPS)",
    )
    parser.add_argument(
        "--quality",
        default=None,
        help="Visual quality preset (1..15 or low, retro, balanced, classic, high, super, ultra, master, cinema, titan, overkill, godlike, monolith, singularity, infinite)",
    )
    parser.add_argument(
        "--color-mode",
        type=str,
        default="truecolor",
        help="Color theme / grading mode ('truecolor', 'grayscale', 'green', 'amber', 'cyberpunk')",
    )
    parser.add_argument(
        "--chars",
        type=str,
        default=DEFAULT_RAMP,
        help="ASCII luminance ramp from dark to bright",
    )
    parser.add_argument(
        "--crt",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable vintage CRT scanlines and phosphor bloom by default",
    )
    parser.add_argument(
        "--seek-step",
        type=float,
        default=5.0,
        help="Interval in seconds for left/right seeking (default: 5.0)",
    )
    parser.add_argument(
        "--audio",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include audio track in exported project (use --no-audio for silent)",
    )
    parser.add_argument(
        "--loop",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable infinite looping by default in exported project",
    )
    parser.add_argument(
        "--build-exe",
        "-b",
        action="store_true",
        default=False,
        help="Automatically compile standalone single-file .exe with PyInstaller after export",
    )
    parser.add_argument(
        "--overwrite",
        "-f",
        action="store_true",
        default=False,
        help="Overwrite destination directory if it already exists",
    )
    parser.add_argument(
        "--lang",
        choices=["tr", "en"],
        default="tr",
        help="Interface language for diagnostics and messages (tr or en)",
    )
    parser.add_argument(
        "--gui-progress",
        action="store_true",
        default=False,
        help="Emit real-time JSON progress lines to stdout for GUI tracking",
    )

    return parser


def export_video(
    video_path: str,
    output_dir: str | None = None,
    cols: int = 80,
    fps: float | None = None,
    chars: str = DEFAULT_RAMP,
    crt: bool = False,
    overwrite: bool = False,
    lang: str = "tr",
    char_aspect: float = 0.55,
    progress_callback: Callable[[int, int, float, float], None] | None = None,
    build_exe: bool = False,
    audio: bool = True,
    loop: bool = False,
    gui_progress: bool = False,
    color_mode: str = "truecolor",
    seek_step: float = 5.0,
) -> str:
    """
    Export a video into a self-contained portable ASCII player directory.

    Args:
        video_path: Path to the input video file.
        output_dir: Destination project directory path.
        cols: Target character columns (clamped to 20..450).
        fps: Target framerate cap (optional).
        chars: ASCII luminance ramp string.
        crt: Whether CRT effects are enabled by default in config.json.
        overwrite: Whether to overwrite existing destination directory.
        lang: Diagnostic output language ('tr' or 'en').
        char_aspect: Font width to height aspect ratio (~0.55).
        progress_callback: Optional callback(current_frame, total_frames, fps, eta).
        build_exe: Automatically compile single-file .exe via PyInstaller.
        audio: Whether to extract and bundle synchronized audio stream.
        loop: Whether infinite loop is enabled by default in config.json.
        gui_progress: Emit JSON progress lines for GUI live bar tracking.
        color_mode: Color theme palette ('truecolor', 'grayscale', 'green', 'amber', 'cyberpunk').

    Returns:
        Absolute normalized path to the created output directory.

    Raises:
        FileNotFoundError: If input video does not exist.
        FileExistsError: If destination exists and overwrite is False.
        ValueError: If video is invalid or empty.
    """
    if not video_path:
        raise ValueError(
            "[HATA / ERROR] Video yolu boş olamaz / Video path cannot be empty"
        )
    if fps is not None and (not math.isfinite(fps) or fps <= 0):
        raise ValueError("[HATA / ERROR] FPS must be finite and greater than zero")

    resolved_video = os.path.abspath(video_path)
    if not os.path.exists(resolved_video):
        raise FileNotFoundError(
            f"[HATA / ERROR] Video dosyası bulunamadı / Video file not found: {video_path}"
        )

    if os.path.getsize(resolved_video) == 0:
        raise ValueError(
            f"[HATA / ERROR] Video dosyası boş (0 bayt) / Video file is empty: {video_path}"
        )

    # Determine destination directory
    if output_dir is None:
        dest_dir = get_video_output_dir(resolved_video, "output")
    else:
        dest_dir = os.path.abspath(output_dir)

    # Check directory existence
    if os.path.exists(dest_dir):
        if not overwrite:
            raise FileExistsError(
                f"[UYARI / WARNING] Çıktı klasörü zaten mevcut / Destination already exists: {dest_dir}. "
                "Üzerine yazmak için --overwrite parametresini kullanın / Use --overwrite to overwrite."
            )
    else:
        os.makedirs(dest_dir, exist_ok=True)

    # Clamp columns to safe bounds (20..450)
    safe_cols = max(20, min(450, int(cols)))

    # 1. Initialize Decoders
    try:
        decoder = VideoDecoder(
            video_path=resolved_video,
            target_cols=safe_cols,
            char_aspect=char_aspect,
            char_ramp=chars,
        )
    except Exception as exc:
        raise ValueError(
            f"[HATA / ERROR] Video çözücü başlatılamadı / Failed initializing video decoder: {exc}"
        ) from exc

    meta = decoder.get_metadata()
    actual_rows = decoder.rows
    actual_cols = decoder.cols
    target_fps = min(fps, meta.fps) if fps is not None else meta.fps
    total_expected_frames = meta.total_frames if meta.total_frames > 0 else int(meta.duration * target_fps)
    if fps is not None:
        total_expected_frames = math.ceil(meta.duration * target_fps)

    # Informational header
    if lang == "tr":
        print("====================================================================")
        print("           RETRO ASCII PROJE DISA AKTARICI / EXPORTER              ")
        print("====================================================================")
        print(f"Girdi Videosu  : {os.path.basename(resolved_video)} ({meta.width}x{meta.height}, {meta.fps:.2f} fps)")
        print(f"Sure           : {meta.duration:.2f} saniye (~{total_expected_frames} kare)")
        print(f"ASCII Grid     : {actual_cols} sutun x {actual_rows} satir")
        print(f"Hedef Klasor   : {dest_dir}")
        print("--------------------------------------------------------------------")
    else:
        print("====================================================================")
        print("             RETRO ASCII PROJECT EXPORTER & BUNDLER                 ")
        print("====================================================================")
        print(f"Input Video    : {os.path.basename(resolved_video)} ({meta.width}x{meta.height}, {meta.fps:.2f} fps)")
        print(f"Duration       : {meta.duration:.2f} seconds (~{total_expected_frames} frames)")
        print(f"ASCII Grid     : {actual_cols} cols x {actual_rows} rows")
        print(f"Destination    : {dest_dir}")
        print("--------------------------------------------------------------------")

    # 2. Extract Audio Stream (asynchronous background thread to overlap with video decoding)
    audio_wav_path = os.path.join(dest_dir, "audio.wav")
    has_audio = False
    audio_thread: threading.Thread | None = None

    def _extract_audio_worker() -> None:
        nonlocal has_audio
        try:
            audio_engine = AudioEngine(resolved_video)
            if audio_engine.has_audio:
                extracted = audio_engine.extract_audio_file(audio_wav_path)
                if extracted and os.path.exists(audio_wav_path) and os.path.getsize(audio_wav_path) > 0:
                    has_audio = True
        except (av.FFmpegError, OSError, RuntimeError) as exc:
            logger.warning("Failed extracting audio: %s", exc)

    if audio:
        audio_thread = threading.Thread(target=_extract_audio_worker, daemon=True)
        audio_thread.start()

    # 3. Process Video Frames
    all_chars: list[np.ndarray] = []
    all_colors: list[np.ndarray] = []

    t_start = time.perf_counter()
    frame_count = 0
    last_json_time = 0.0

    try:
        frames = decoder.iter_frames_at_fps(target_fps) if fps is not None else decoder.iter_frames()
        for _pts, char_indices, rgb_colors in frames:
            all_chars.append(char_indices)
            all_colors.append(rgb_colors)
            frame_count += 1

            # Progress computation
            elapsed = time.perf_counter() - t_start
            cur_fps = frame_count / elapsed if elapsed > 0 else 0.0
            tot = max(frame_count, total_expected_frames)
            pct = min(100.0, (frame_count / tot) * 100.0) if tot > 0 else 0.0
            remaining_frames = max(0, tot - frame_count)
            eta = remaining_frames / cur_fps if cur_fps > 0 else 0.0

            # Progress bar representation (encoding safe)
            bar_len = 24
            filled_len = int(bar_len * (pct / 100.0))
            can_unicode = False
            try:
                "█░".encode(sys.stdout.encoding or "utf-8")
                can_unicode = True
            except (UnicodeEncodeError, LookupError, AttributeError):
                can_unicode = False

            if can_unicode:
                bar = "█" * filled_len + "░" * (bar_len - filled_len)
            else:
                bar = "=" * filled_len + "-" * (bar_len - filled_len)

            progress_line = (
                f"\r[{bar}] {pct:5.1f}% ({frame_count}/{tot}) | {cur_fps:5.1f} FPS | ETA: {eta:4.1f}s"
            )

            if gui_progress:
                now = time.perf_counter()
                if now - last_json_time >= 0.033 or frame_count >= tot:
                    last_json_time = now
                    # Scale frame conversion progress: 0-68% if build_exe, else 0-85%
                    max_frame_pct = 68.0 if build_exe else 85.0
                    overall_pct = min(max_frame_pct, max(0.0, (frame_count / tot) * max_frame_pct)) if tot > 0 else 0.0
                    bar_ui = "█" * int(20 * overall_pct / 100.0) + "░" * (20 - int(20 * overall_pct / 100.0))
                    text_ui = f"[{bar_ui}] {overall_pct:5.1f}% ({frame_count}/{tot}) | {cur_fps:5.1f} FPS | ETA: {eta:4.1f}s"
                    p_info = {
                        "type": "progress",
                        "pct": round(overall_pct, 1),
                        "frame_pct": round(pct, 1),
                        "scaled_pct": round(overall_pct, 1),
                        "current": frame_count,
                        "total": tot,
                        "fps": round(cur_fps, 1),
                        "eta": round(eta, 1),
                        "bar": bar_ui,
                        "text": text_ui,
                        "stage": f"ASCII Kareleri Çözülüyor ({frame_count}/{tot})",
                    }
                    sys.stdout.write(f"\n__PROGRESS_JSON__{json.dumps(p_info)}\n")
                    sys.stdout.flush()
            else:
                try:
                    sys.stdout.write(progress_line)
                    sys.stdout.flush()
                except (UnicodeEncodeError, OSError):
                    fallback = progress_line.encode("ascii", errors="replace").decode("ascii")
                    try:
                        sys.stdout.write(fallback)
                        sys.stdout.flush()
                    except OSError:
                        pass

            if progress_callback is not None:
                progress_callback(frame_count, tot, cur_fps, eta)
    finally:
        decoder.close()
        if audio_thread is not None:
            audio_thread.join()

    if has_audio and os.path.exists(audio_wav_path) and os.path.getsize(audio_wav_path) > 0:
        wav_mb = os.path.getsize(audio_wav_path) / (1024 * 1024)
        if lang == "tr":
            print(f"[OK] Ses akisi basariyla cikarildi: audio.wav ({wav_mb:.2f} MB, 44.1kHz stereo)")
        else:
            print(f"[OK] Audio stream exported: audio.wav ({wav_mb:.2f} MB, 44.1kHz stereo)")
    else:
        has_audio = False
        if os.path.exists(audio_wav_path):
            try:
                os.remove(audio_wav_path)
            except OSError:
                pass
        if lang == "tr":
            print("[BILGI] Videoda ses akisi bulunamadi, sessiz modda aktariliyor.")
        else:
            print("[INFO] No audio stream detected, exporting in silent mode.")

    if not gui_progress:
        try:
            sys.stdout.write("\n")
            sys.stdout.flush()
        except OSError:
            pass

    if frame_count == 0:
        raise ValueError(
            "[HATA / ERROR] Videodan hiçbir kare çözülemedi / No frames could be decoded from video"
        )

    # 4. Serialize and Compress into ascii_data.npz
    if gui_progress:
        npz_pct = 71.0 if build_exe else 92.0
        bar_npz = "█" * int(20 * npz_pct / 100.0) + "░" * (20 - int(20 * npz_pct / 100.0))
        p_info = {
            "type": "progress",
            "pct": npz_pct,
            "scaled_pct": npz_pct,
            "current": frame_count,
            "total": tot,
            "fps": 0.0,
            "eta": 0.0,
            "bar": bar_npz,
            "text": f"[{bar_npz}] {npz_pct:5.1f}% | Veri seti sıkıştırılıyor...",
            "stage": "[NPZ] ASCII veri seti kaydediliyor (ascii_data.npz)...",
        }
        sys.stdout.write(f"\n__PROGRESS_JSON__{json.dumps(p_info)}\n")
        sys.stdout.flush()

    chars_array = np.ascontiguousarray(np.stack(all_chars, axis=0), dtype=np.uint8)
    colors_array = np.ascontiguousarray(np.stack(all_colors, axis=0), dtype=np.uint8)

    npz_path = os.path.join(dest_dir, "ascii_data.npz")
    save_npz_fast(npz_path, 1, chars=chars_array, colors=colors_array)

    raw_bytes = chars_array.nbytes + colors_array.nbytes
    comp_bytes = os.path.getsize(npz_path)
    ratio = raw_bytes / comp_bytes if comp_bytes > 0 else 1.0

    raw_mb = raw_bytes / (1024 * 1024)
    comp_mb = comp_bytes / (1024 * 1024)

    if lang == "tr":
        print(f"[OK] ASCII veri seti kaydedildi: ascii_data.npz (Ham: {raw_mb:.2f} MB -> Sikistirilmis: {comp_mb:.2f} MB, Oran: {ratio:.1f}x)")
    else:
        print(f"[OK] ASCII dataset serialized: ascii_data.npz (Raw: {raw_mb:.2f} MB -> Compressed: {comp_mb:.2f} MB, Ratio: {ratio:.1f}x)")

    # 5. Write config.json
    config_dict = {
        "version": "1.0.0",
        "source_video": os.path.basename(resolved_video),
        "cols": actual_cols,
        "rows": actual_rows,
        "fps": target_fps,
        "total_frames": frame_count,
        "duration_seconds": round(meta.duration, 2),
        "aspect_ratio": round(meta.width / meta.height, 4) if meta.height > 0 else 1.7778,
        "has_audio": has_audio,
        "audio_enabled": has_audio and audio,
        "audio_file": "audio.wav" if has_audio else "",
        "data_file": "ascii_data.npz",
        "char_ramp": chars,
        "color_mode": color_mode,
        "crt_default": crt,
        "loop_default": loop,
        "seek_step": float(seek_step),
        "fullscreen_default": False,
        "show_hud": False,
        "window_title": os.path.basename(resolved_video),
    }

    config_path = os.path.join(dest_dir, "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_dict, f, indent=2)

    if lang == "tr":
        print("[OK] Yapilandirma dosyasi olusturuldu: config.json")
    else:
        print("[OK] Configuration generated: config.json")

    # 6. Copy Standalone Template Artifacts & Icons
    template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "standalone_template")
    template_files = [
        "run.py",
        "help_overlay.py",
        "run.bat",
        "build_exe.bat",
        "README.txt",
        "standalone_player.spec",
        "eye_icon.png",
        "eye_icon.ico",
    ]

    for fname in template_files:
        src_file = os.path.join(template_dir, fname)
        dst_file = os.path.join(dest_dir, fname)
        if os.path.exists(src_file):
            shutil.copy2(src_file, dst_file)
        else:
            logger.warning("Template file not found: %s", src_file)

    # 7. Optional: Build standalone single-file EXE via PyInstaller
    if build_exe:
        if lang == "tr":
            print("[INFO] PyInstaller ile tek dosya .exe derleniyor...")
        else:
            print("[INFO] Compiling standalone single-file .exe with PyInstaller...")

        if gui_progress:
            init_pct = 74.0
            bar_init = "█" * int(20 * init_pct / 100.0) + "░" * (20 - int(20 * init_pct / 100.0))
            p_info = {
                "type": "progress",
                "pct": init_pct,
                "scaled_pct": init_pct,
                "current": total_expected_frames,
                "total": total_expected_frames,
                "fps": 0.0,
                "eta": 0.0,
                "bar": bar_init,
                "text": f"[{bar_init}] {init_pct:5.1f}% | [PyInstaller] Başlatılıyor...",
                "stage": "[PyInstaller] Bağımsız tek dosya .EXE derleniyor...",
            }
            sys.stdout.write(f"\n__PROGRESS_JSON__{json.dumps(p_info)}\n")
            sys.stdout.flush()

        spec_file = os.path.join(dest_dir, "standalone_player.spec")
        try:
            popen_kwargs: dict = {}
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            proc = subprocess.Popen(
                [sys.executable, "-m", "PyInstaller", spec_file, "--distpath", ".", "--workpath", "build_temp", "--clean", "-y"],
                cwd=dest_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
                **popen_kwargs,
            )
            py_pct = 75.0
            if proc.stdout is not None:
                for raw_line in proc.stdout:
                    line_str = raw_line.strip()
                    if not line_str:
                        continue
                    if "Analysis" in line_str:
                        py_pct = max(py_pct, min(85.0, py_pct + 0.3))
                        stage_name = "[PyInstaller] Bağımlılıklar taranıyor (Analysis)..."
                    elif "PYZ" in line_str:
                        py_pct = max(85.0, min(92.0, py_pct + 0.5))
                        stage_name = "[PyInstaller] Python arşivi paketleniyor (PYZ)..."
                    elif "EXE" in line_str or "Appending" in line_str:
                        py_pct = max(92.0, min(98.0, py_pct + 0.4))
                        stage_name = "[PyInstaller] ASCII_Player.exe yazılıyor (EXE)..."
                    elif "completed successfully" in line_str:
                        py_pct = 99.0
                        stage_name = "[PyInstaller] Derleme tamamlandı!"
                    else:
                        py_pct = min(98.0, py_pct + 0.08)
                        stage_name = f"[PyInstaller] {line_str[:55]}"

                    if gui_progress:
                        bar_p = "█" * int(20 * py_pct / 100.0) + "░" * (20 - int(20 * py_pct / 100.0))
                        msg = {
                            "type": "progress",
                            "pct": round(py_pct, 1),
                            "scaled_pct": round(py_pct, 1),
                            "current": total_expected_frames,
                            "total": total_expected_frames,
                            "fps": 0.0,
                            "eta": 0.0,
                            "bar": bar_p,
                            "text": f"[{bar_p}] {py_pct:.1f}% | {stage_name}",
                            "stage": stage_name,
                        }
                        sys.stdout.write(f"\n__PROGRESS_JSON__{json.dumps(msg)}\n")
                        sys.stdout.flush()
                    else:
                        print(f"[PyInstaller] {line_str}")

            proc.wait()
            temp_build = os.path.join(dest_dir, "build_temp")
            if os.path.exists(temp_build):
                shutil.rmtree(temp_build, ignore_errors=True)

            exe_path = os.path.join(dest_dir, "ASCII_Player.exe")
            if proc.returncode != 0 or not os.path.exists(exe_path):
                raise RuntimeError(
                    f"PyInstaller derlemesi başarısız oldu (Hata Kodu: {proc.returncode})"
                )

            if gui_progress:
                sys.stdout.write(f"\n__PROGRESS_JSON__{json.dumps({'type': 'progress', 'pct': 100.0, 'stage': '[BAŞARILI] ASCII_Player.exe üretildi!', 'bar': '█' * 20, 'text': '[████████████████████] 100.0% | EXE Derlemesi Tamamlandı!'})}\n")
                sys.stdout.flush()
            if lang == "tr":
                print(f"[BASARILI] EXE olusturuldu: {exe_path}")
            else:
                print(f"[SUCCESS] Standalone .exe compiled successfully: {exe_path}")
        except (subprocess.SubprocessError, OSError, RuntimeError) as exc:
            logger.error("PyInstaller compilation failed: %s", exc)
            raise
    else:
        if gui_progress:
            sys.stdout.write(f"\n__PROGRESS_JSON__{json.dumps({'type': 'progress', 'pct': 100.0, 'stage': '[BAŞARILI] ASCII projesi oluşturuldu!', 'bar': '█' * 20, 'text': '[████████████████████] 100.0% | ASCII Projesi Tamamlandı!'})}\n")
            sys.stdout.flush()

    # 8. Print Completion Summary
    if lang == "tr":
        print("--------------------------------------------------------------------")
        print(f"[BASARILI] Bagimsiz ASCII projesi tamamlandi: {dest_dir}")
        print("Klasor icindeki 'ASCII_Player.exe' veya 'run.bat' ile baslatabilirsiniz!")
        print("====================================================================")
    else:
        print("--------------------------------------------------------------------")
        print(f"[SUCCESS] Standalone ASCII project created: {dest_dir}")
        print("Launch by double-clicking 'ASCII_Player.exe' or 'run.bat' inside directory!")
        print("====================================================================")

    return dest_dir


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for ascii_exporter."""
    parser = create_parser()
    args = parser.parse_args(argv)

    cols = args.cols
    chars = args.chars

    if args.quality:
        q_key = str(args.quality).strip().lower()
        if q_key in QUALITY_LOOKUP:
            q_cfg = QUALITY_LOOKUP[q_key]
            if args.cols == 80:
                cols = q_cfg["cols"]
            if args.chars == DEFAULT_RAMP:
                chars = q_cfg["chars"]

    try:
        final_dir = export_video(
            video_path=args.input,
            output_dir=args.output,
            cols=cols,
            fps=args.fps,
            chars=chars,
            crt=args.crt,
            overwrite=args.overwrite,
            lang=args.lang,
            build_exe=args.build_exe,
            audio=args.audio,
            loop=args.loop,
            gui_progress=getattr(args, "gui_progress", False),
            color_mode=args.color_mode,
            seek_step=getattr(args, "seek_step", 5.0),
        )
        if getattr(args, "gui_progress", False):
            sys.stdout.write(f"\n__PROGRESS_JSON__{json.dumps({'type': 'done', 'success': True, 'output': final_dir, 'folder': final_dir})}\n")
            sys.stdout.flush()
        return EXIT_SUCCESS
    except FileNotFoundError as exc:
        if getattr(args, "gui_progress", False):
            sys.stdout.write(f"\n__PROGRESS_JSON__{json.dumps({'type': 'done', 'success': False, 'error': str(exc)})}\n")
            sys.stdout.flush()
        print(f"{exc}", file=sys.stderr)
        return EXIT_FILE_NOT_FOUND
    except FileExistsError as exc:
        if getattr(args, "gui_progress", False):
            sys.stdout.write(f"\n__PROGRESS_JSON__{json.dumps({'type': 'done', 'success': False, 'error': str(exc)})}\n")
            sys.stdout.flush()
        print(f"{exc}", file=sys.stderr)
        return EXIT_FILE_NOT_FOUND
    except (ValueError, OSError, RuntimeError, av.error.InvalidDataError) as exc:
        if getattr(args, "gui_progress", False):
            sys.stdout.write(f"\n__PROGRESS_JSON__{json.dumps({'type': 'done', 'success': False, 'error': str(exc)})}\n")
            sys.stdout.flush()
        print(f"{exc}", file=sys.stderr)
        return EXIT_FORMAT_ERROR
    except KeyboardInterrupt:
        if getattr(args, "gui_progress", False):
            sys.stdout.write(f"\n__PROGRESS_JSON__{json.dumps({'type': 'done', 'success': False, 'error': 'İptal edildi'})}\n")
            sys.stdout.flush()
        return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
