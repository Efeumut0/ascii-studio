"""Generate test patterns and stereo tones without using personal media."""

import os
import tempfile
from fractions import Fraction
from pathlib import Path

import av
import numpy as np


def make_clip(path, *, frames, audio_duration, width=720, height=1280):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".mp4", delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with av.open(str(temporary_path), "w") as output:
            video = output.add_stream("libx264", rate=30)
            video.width, video.height = width, height
            video.pix_fmt = "yuv420p"
            video.options = {"preset": "ultrafast", "crf": "30"}
            audio = output.add_stream("aac", rate=44100)
            audio.layout = "stereo"
            pattern = np.zeros((height, width, 3), dtype=np.uint8)
            pattern[:, :, 0] = np.linspace(0, 255, width, dtype=np.uint8)
            pattern[:, :, 1] = np.linspace(0, 255, height, dtype=np.uint8)[:, None]
            pattern[:, :, 2] = 96
            for index in range(frames):
                image = pattern.copy()
                x = index * 7 % width
                image[:, x:min(width, x + max(2, width // 12))] = (240, 210, 150)
                frame = av.VideoFrame.from_ndarray(image, format="rgb24")
                frame.pts, frame.time_base = index, Fraction(1, 30)
                for packet in video.encode(frame):
                    output.mux(packet)
            for packet in video.encode():
                output.mux(packet)
            samples = round(audio_duration * 44100)
            for offset in range(0, samples, 1024):
                times = np.arange(offset, min(samples, offset + 1024)) / 44100
                tones = np.stack((0.15 * np.sin(2 * np.pi * 440 * times),
                                  0.15 * np.sin(2 * np.pi * 660 * times))).astype(np.float32)
                frame = av.AudioFrame.from_ndarray(tones, format="fltp", layout="stereo")
                frame.sample_rate = 44100
                frame.pts, frame.time_base = offset, Fraction(1, 44100)
                for packet in audio.encode(frame):
                    output.mux(packet)
            for packet in audio.encode():
                output.mux(packet)
        os.link(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main():
    root = Path(__file__).resolve().parents[1]
    for name, frames, duration in (("test.mp4", 314, 10.726), ("asci.mp4", 1932, 64.525)):
        target = root / name
        if target.exists():
            print(f"Keeping existing {name}")
        else:
            make_clip(target, frames=frames, audio_duration=duration)
            print(f"Generated {name}")


if __name__ == "__main__":
    main()
