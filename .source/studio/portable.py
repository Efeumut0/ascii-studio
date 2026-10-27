import json
import math
import os
import shutil
import tempfile
import wave
import zipfile
from pathlib import Path

import av
import numpy as np

from ascii_engine.video_decoder import VideoDecoder
from ascii_exporter import QUALITY_PRESET_MAP


def stream_audio(video, output):
    with av.open(str(video)) as container:
        if not container.streams.audio:
            return False
        resampler = av.AudioResampler(format="s16", layout="stereo", rate=44100)
        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(44100)
            for frame in container.decode(container.streams.audio[0]):
                for converted in resampler.resample(frame):
                    wav.writeframesraw(converted.to_ndarray().tobytes())
            for converted in resampler.resample(None):
                wav.writeframesraw(converted.to_ndarray().tobytes())
        return output.stat().st_size > 44


def write_array_file(raw_path, target_path, shape):
    with target_path.open("wb") as target:
        np.lib.format.write_array_header_2_0(target, {"descr": "|u1", "fortran_order": False, "shape": shape})
        with raw_path.open("rb") as raw:
            shutil.copyfileobj(raw, target, length=1024 * 1024)


def export_portable(video, output, settings, stub, report, stage_root=None):
    settings.validate()
    video, output, stub = Path(video), Path(output), Path(stub)
    if not video.is_file():
        raise FileNotFoundError(str(video))
    if not stub.is_file():
        raise FileNotFoundError("Portable player runtime is missing")
    output.parent.mkdir(parents=True, exist_ok=True)
    preset = QUALITY_PRESET_MAP[settings.quality]
    ramp = settings.char_ramp or preset["chars"]
    cols = settings.cols or preset["cols"]
    with tempfile.TemporaryDirectory(prefix=".ascii-export-", dir=stage_root or output.parent) as folder:
        stage = Path(folder)
        report(stage="starting", percent=0)
        with VideoDecoder(str(video), cols, settings.char_aspect, ramp) as decoder:
            metadata = decoder.get_metadata()
            fps = min(settings.fps or metadata.fps, 60)
            expected = max(1, math.ceil(metadata.duration * fps))
            count = 0
            raw_chars = stage / "chars.raw"
            raw_colors = stage / "colors.raw"
            with raw_chars.open("wb") as chars_file, raw_colors.open("wb") as colors_file:
                for _, chars, colors in decoder.iter_frames_at_fps(fps):
                    chars_file.write(chars.tobytes())
                    colors_file.write(colors.tobytes())
                    count += 1
                    if count == 1 or count % 10 == 0 or count >= expected:
                        report(stage="decode", percent=min(82, count / expected * 82), current=count, total=expected)
            if count == 0:
                raise ValueError("No video frames could be decoded")
            shape = (count, decoder.rows, decoder.cols)
            write_array_file(raw_chars, stage / "chars.npy", shape)
            write_array_file(raw_colors, stage / "colors.npy", (*shape, 3))
        raw_chars.unlink()
        raw_colors.unlink()
        report(stage="audio_stage", percent=83)
        has_audio = settings.audio and stream_audio(video, stage / "audio.wav")
        config = {
            "version": "2.0", "source_video": video.name, "window_title": video.name,
            "cols": shape[2], "rows": shape[1], "fps": fps, "total_frames": count,
            "duration_seconds": count / fps, "aspect_ratio": metadata.aspect_ratio,
            "has_audio": bool(has_audio), "audio_enabled": bool(has_audio),
            "audio_file": "audio.wav" if has_audio else "", "data_file": "chars.npy",
            "colors_file": "colors.npy", "char_ramp": ramp, "color_mode": settings.color_mode,
            "crt_default": settings.crt, "loop_default": settings.loop, "seek_step": settings.seek_step,
            "show_hud": settings.hud, "fullscreen_default": False, "language": settings.language,
            "font_size": settings.font_size,
        }
        (stage / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        packed = stage / "player.exe"
        shutil.copyfile(stub, packed)
        names = ["config.json", "chars.npy", "colors.npy"] + (["audio.wav"] if has_audio else [])
        total_bytes = sum((stage / name).stat().st_size for name in names)
        copied = 0
        with zipfile.ZipFile(packed, "a", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            for name in names:
                with (stage / name).open("rb") as source, archive.open(name, "w", force_zip64=True) as target:
                    while chunk := source.read(1024 * 1024):
                        target.write(chunk)
                        copied += len(chunk)
                        report(stage="pack", percent=85 + copied / max(1, total_bytes) * 14)
        with zipfile.ZipFile(packed) as archive:
            if archive.testzip() is not None:
                raise ValueError("Export archive verification failed")
        os.replace(packed, output)
        report(stage="finished", percent=100, success=True, output=str(output))
        return output
