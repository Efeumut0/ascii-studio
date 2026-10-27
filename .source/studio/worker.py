import json
import os
import sys
import time
import traceback
import zipfile
from pathlib import Path

import av
import pygame

from studio.model import StudioSettings, resource_path, save_json


def run_worker(request_path):
    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    settings = StudioSettings(**request["settings"]).validate()
    log = Path(request["log"])
    log.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout = log.open("w", encoding="utf-8", buffering=1)
    sys.stderr = sys.stdout
    progress_path = Path(request["progress"])
    last_update = 0

    def report(**event):
        nonlocal last_update
        now = time.monotonic()
        if now - last_update < 0.1 and event.get("percent", 0) < 100 and event.get("current", 1) != 1:
            return
        last_update = now
        save_json(progress_path, event)

    try:
        if request["action"] == "play":
            from ascii_exporter import QUALITY_PRESET_MAP
            from ascii_player import play_video

            preset = QUALITY_PRESET_MAP[settings.quality]
            return play_video(request["video"], cols=settings.cols or preset["cols"],
                              fps=settings.fps or None, chars=settings.char_ramp or preset["chars"],
                              crt=settings.crt, font_size=settings.font_size or 12, lang=settings.language,
                              char_aspect=settings.char_aspect, loop=settings.loop, audio=settings.audio,
                              quality=preset["id"], color_mode=settings.color_mode,
                              seek_step=settings.seek_step, hud=settings.hud,
                              max_duration=request.get("max_duration"))
        if request["action"] == "export":
            from studio.portable import export_portable

            export_portable(request["video"], request["output"], settings,
                            resource_path("assets/portable-player.exe"), report, stage_root=Path(request_path).parent)
        elif request["action"] == "render":
            from ascii_video_renderer import render_video_to_mp4

            output = Path(request["output"])
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = Path(request_path).parent / "render.mp4"
            report(stage="render_stage", percent=0)

            def on_progress(current, total, fps, eta):
                report(stage="render_stage", percent=min(98, current / max(1, total) * 98),
                       current=current, total=total, fps=fps, eta=max(0, eta))

            render_video_to_mp4(request["video"], str(temporary), preset=settings.quality,
                                cols=settings.cols or None, fps=settings.fps or None,
                                chars=settings.char_ramp or None, font_size=settings.font_size or None,
                                crt=settings.crt, audio=settings.audio, color_mode=settings.color_mode,
                                char_aspect=settings.char_aspect, progress_callback=on_progress,
                                encoder_preset=settings.encoder_preset, workers=settings.workers or None,
                                resolution=settings.resolution, crf=settings.crf)
            with av.open(str(temporary)) as container:
                if not container.streams.video or next(container.decode(video=0), None) is None:
                    raise ValueError("The rendered video has no playable frames")
            os.replace(temporary, output)
            report(stage="finished", percent=100, success=True, output=str(output))
        else:
            raise ValueError("Unknown action")
        return 0
    except (OSError, ValueError, RuntimeError, TypeError, av.FFmpegError, pygame.error, zipfile.BadZipFile) as error:
        traceback.print_exc()
        save_json(progress_path, {"stage": "error", "percent": 0, "success": False, "error": str(error)})
        return 1
    finally:
        sys.stdout.flush()
