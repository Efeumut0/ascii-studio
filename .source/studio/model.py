import json
import math
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path


@dataclass
class StudioSettings:
    language: str = "tr"
    quality: str = "5"
    cols: int = 0
    char_ramp: str = ""
    color_mode: str = "truecolor"
    resolution: str = "1080p"
    fps: float = 0
    font_size: int = 0
    char_aspect: float = 0.55
    audio: bool = True
    crt: bool = False
    loop: bool = False
    hud: bool = False
    seek_step: float = 5
    encoder_preset: str = "veryfast"
    workers: int = 0
    crf: int = 20
    output_root: str = ""

    def validate(self):
        if self.language not in ("tr", "en") or self.quality not in [str(index) for index in range(1, 16)]:
            raise ValueError("Invalid language or quality")
        for value in (self.fps, self.char_aspect, self.seek_step):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("Numeric settings must be finite")
        for value in (self.cols, self.font_size, self.workers, self.crf):
            if not isinstance(value, int):
                raise TypeError("Integer setting required")
        if self.cols != 0 and not 20 <= self.cols <= 450:
            raise ValueError("Columns must be 20–450, or 0 for preset")
        if not isinstance(self.char_ramp, str) or len(self.char_ramp) > 256:
            raise ValueError("Character ramp must have at most 256 characters")
        if self.fps != 0 and not 1 <= self.fps <= 60:
            raise ValueError("FPS must be 1–60, or 0 for source")
        if not 0.1 <= self.char_aspect <= 2 or not 1 <= self.seek_step <= 600:
            raise ValueError("Invalid character aspect or seek step")
        if self.font_size != 0 and not 3 <= self.font_size <= 48:
            raise ValueError("Font size must be 3–48, or 0 for automatic")
        if not 0 <= self.workers <= 32 or not 0 <= self.crf <= 51:
            raise ValueError("Invalid worker count or CRF")
        if self.color_mode not in ("truecolor", "grayscale", "green", "amber", "cyberpunk"):
            raise ValueError("Invalid color mode")
        if self.encoder_preset not in ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"):
            raise ValueError("Invalid encoder preset")
        if self.resolution not in ("auto", "720p", "1080p", "2k", "4k", "original"):
            parts = self.resolution.lower().split("x")
            if len(parts) != 2 or not all(part.isdigit() for part in parts):
                raise ValueError("Resolution must be a preset or WIDTHxHEIGHT")
            if not all(64 <= int(part) <= 7680 for part in parts):
                raise ValueError("Custom resolution is outside supported bounds")
        if not isinstance(self.output_root, str):
            raise TypeError("Output folder must be a path")
        for value in (self.audio, self.crt, self.loop, self.hud):
            if not isinstance(value, bool):
                raise TypeError("Boolean setting required")
        return self


def application_paths(root=None):
    if root is None:
        if getattr(sys, "frozen", False):
            root = Path(sys.executable).resolve().parent
        else:
            source_root = Path(__file__).resolve().parents[1]
            root = source_root.parent if source_root.name == ".source" else source_root
    root = Path(root).resolve()
    return {"root": root, "videos": root / "videos", "output": root / "output", "state": root / ".state"}


def resource_path(name):
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / name


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(pending, path)


def save_settings(path, settings):
    settings.validate()
    save_json(path, asdict(settings))


def load_settings(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return StudioSettings()
        known = {field.name for field in fields(StudioSettings)}
        return StudioSettings(**{key: value for key, value in data.items() if key in known}).validate()
    except (OSError, ValueError, TypeError, AttributeError):
        return StudioSettings()
