"""Play video as colored ASCII with audio and keyboard controls."""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import sys
import time
from collections.abc import Sequence

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

# Pre-set headless drivers if invoked with --headless or via environment
if "--headless" in sys.argv or os.environ.get("SDL_VIDEODRIVER") == "dummy":
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame

from ascii_engine.audio_engine import AudioEngine
from ascii_engine.video_decoder import VideoDecoder, VideoMetadata
from ascii_ui.crt_effects import CrtEffect
from ascii_ui.hud import HudRenderer, PlayerState
from ascii_ui.input_handler import InputHandler
from ascii_ui.renderer import (
    CLASSIC_16_RAMP,
    DEFAULT_RAMP,
    DETAILED_RAMP,
    EXTENDED_92_RAMP,
    AsciiRenderer,
)

logger = logging.getLogger(__name__)

EXIT_SUCCESS = 0
EXIT_FILE_NOT_FOUND = 1
EXIT_FORMAT_ERROR = 2

# Quality presets
QUALITY_PRESET_MAP: dict[str, dict] = {
    "1": {"id": "low", "cols": 50, "chars": DEFAULT_RAMP, "font_size": 14, "scale": 0.50},
    "2": {"id": "retro", "cols": 65, "chars": DEFAULT_RAMP, "font_size": 13, "scale": 0.56},
    "3": {"id": "balanced", "cols": 80, "chars": CLASSIC_16_RAMP, "font_size": 12, "scale": 0.62},
    "4": {"id": "classic", "cols": 95, "chars": CLASSIC_16_RAMP, "font_size": 11, "scale": 0.67},
    "5": {"id": "high", "cols": 110, "chars": DETAILED_RAMP, "font_size": 10, "scale": 0.72},
    "6": {"id": "super", "cols": 125, "chars": DETAILED_RAMP, "font_size": 9, "scale": 0.77},
    "7": {"id": "ultra", "cols": 140, "chars": DETAILED_RAMP, "font_size": 8, "scale": 0.82},
    "8": {"id": "master", "cols": 160, "chars": DETAILED_RAMP, "font_size": 8, "scale": 0.88},
    "9": {"id": "cinema", "cols": 180, "chars": DETAILED_RAMP, "font_size": 7, "scale": 0.92},
    "10": {"id": "titan", "cols": 200, "chars": DETAILED_RAMP, "font_size": 6, "scale": 0.93},
    "11": {"id": "overkill", "cols": 230, "chars": DETAILED_RAMP, "font_size": 6, "scale": 0.94},
    "12": {"id": "godlike", "cols": 260, "chars": EXTENDED_92_RAMP, "font_size": 5, "scale": 0.96},
    "13": {"id": "monolith", "cols": 300, "chars": EXTENDED_92_RAMP, "font_size": 5, "scale": 0.965},
    "14": {"id": "singularity", "cols": 340, "chars": EXTENDED_92_RAMP, "font_size": 4, "scale": 0.97},
    "15": {"id": "infinite", "cols": 380, "chars": EXTENDED_92_RAMP, "font_size": 4, "scale": 0.98},
}

QUALITY_LOOKUP: dict[str, dict] = {}
for k, v in QUALITY_PRESET_MAP.items():
    QUALITY_LOOKUP[k] = v
    QUALITY_LOOKUP[v["id"]] = v
QUALITY_LOOKUP["standard"] = QUALITY_PRESET_MAP["3"]


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


def apply_windows_app_icon(window_surface: pygame.Surface | None = None) -> None:
    """Apply creepy eye icon to Windows process, Pygame window HWND, and console."""
    if sys.platform != "win32":
        return

    import ctypes

    with contextlib.suppress(AttributeError, OSError):
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("retro_ascii_studio.app")

    ico_cands = [
        get_resource_path(os.path.join("assets", "eye_icon.ico")),
        get_resource_path(os.path.join("assets", "icon.ico")),
        get_resource_path("eye_icon.ico"),
        get_resource_path("icon.ico"),
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


class PlayerArgumentParser(argparse.ArgumentParser):
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


def create_parser() -> PlayerArgumentParser:
    """
    Create and configure CLI argument parser for live ASCII player.

    Returns:
        Configured PlayerArgumentParser instance.
    """
    parser = PlayerArgumentParser(
        description="Retro ASCII Video Player with synchronized audio and CRT effects",
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

    # Display and grid options
    parser.add_argument(
        "--cols",
        "-w",
        type=int,
        default=80,
        help="Target character columns (horizontal resolution)",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=None,
        help="Target playback FPS (default from video metadata, capped at 60)",
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
        help="Toggle vintage CRT scanlines and phosphor bloom effects",
    )
    parser.add_argument(
        "--seek-step",
        type=float,
        default=5.0,
        help="Interval in seconds for left/right seeking (default: 5.0)",
    )
    parser.add_argument(
        "--font-size",
        type=int,
        default=12,
        help="Font size for Consolas monospace character cells",
    )
    parser.add_argument(
        "--aspect",
        type=float,
        default=0.55,
        help="Character cell aspect ratio (font width / font height)",
    )
    parser.add_argument(
        "--audio",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable synchronized audio playback (use --no-audio to mute)",
    )

    # Runtime options
    parser.add_argument(
        "--lang",
        choices=["tr", "en"],
        default="tr",
        help="Interface language for diagnostics and messages (tr or en)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run player in headless mode (offscreen dummy display for tests)",
    )
    parser.add_argument(
        "--loop",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Loop playback indefinitely from beginning when video ends",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Maximum playback duration in seconds before terminating (useful for tests)",
    )
    parser.add_argument(
        "--hud",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Toggle retro HUD chrome (header, gutter, status bar) (default: False)",
    )

    return parser


def play_video(
    video_path: str,
    cols: int = 80,
    fps: float | None = None,
    chars: str = DEFAULT_RAMP,
    crt: bool = False,
    font_size: int = 12,
    lang: str = "tr",
    headless: bool = False,
    char_aspect: float = 0.55,
    loop: bool = False,
    max_duration: float | None = None,
    audio: bool = True,
    quality: str | None = None,
    color_mode: str = "truecolor",
    seek_step: float = 5.0,
    hud: bool = False,
) -> int:
    """
    Launch interactive live ASCII video playback with audio synchronization.

    Args:
        video_path: Path to the media file.
        cols: Target character columns.
        fps: Target FPS cap (default from video, capped at 60).
        chars: Character ramp from dark to bright.
        crt: Whether CRT scanlines are enabled by default.
        font_size: Monospace font point size.
        lang: Language for diagnostics ('tr' or 'en').
        headless: Whether to run with dummy video/audio drivers.
        char_aspect: Monospace font width-to-height aspect ratio.
        loop: Whether to loop playback when EOF is reached.
        max_duration: Optional runtime limit in wall-clock seconds.
        audio: Whether audio playback is enabled.
        quality: Optional quality preset name for window sizing calibration.
        color_mode: Color theme palette ('truecolor', 'grayscale', 'green', 'amber', 'cyberpunk').

    Returns:
        Exit code: 0 for success, 1 for file error, 2 for format error.
    """
    if not video_path:
        raise ValueError(
            "[HATA / ERROR] Video yolu boş olamaz / Video path cannot be empty"
        )

    resolved_path = os.path.abspath(video_path)
    if not os.path.exists(resolved_path):
        raise FileNotFoundError(
            f"[HATA / ERROR] Video dosyası bulunamadı / Video file not found: {video_path}"
        )

    if os.path.getsize(resolved_path) == 0:
        raise ValueError(
            f"[HATA / ERROR] Video dosyası boş (0 bayt) / Video file is empty: {video_path}"
        )

    if headless or os.environ.get("SDL_VIDEODRIVER") == "dummy":
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"

    # 1. Initialize Video Decoder
    try:
        decoder = VideoDecoder(
            video_path=resolved_path,
            target_cols=cols,
            char_aspect=char_aspect,
            char_ramp=chars,
        )
    except Exception as exc:
        raise ValueError(
            f"[HATA / ERROR] Dosyada geçerli bir video akışı açılamadı / "
            f"Failed opening video stream: {video_path} ({exc})"
        ) from exc

    metadata: VideoMetadata = decoder.get_metadata()
    target_fps = float(fps) if (fps is not None and fps > 0) else metadata.fps
    target_fps = max(1.0, min(60.0, target_fps))
    frame_duration = 1.0 / target_fps

    # 2. Initialize Audio Engine (respects --audio / --no-audio flag)
    audio_engine: AudioEngine | None = None
    has_audio = False
    if audio:
        try:
            audio_engine = AudioEngine(resolved_path)
            has_audio = audio_engine.has_audio
            if has_audio:
                audio_engine.load_for_playback()
        except (OSError, RuntimeError, pygame.error) as exc:
            logger.debug("Audio initialization bypassed: %s", exc)
            has_audio = False
            audio_engine = None

    # 3. Initialize Pygame subsystems
    pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()

    header_h = HudRenderer.HEADER_HEIGHT if hud else 0
    gutter_w = HudRenderer.GUTTER_WIDTH if hud else 0
    footer_h = HudRenderer.STATUS_BAR_HEIGHT if hud else 0

    # Automatically query desktop display bounds
    info = pygame.display.Info()
    desktop_w = info.current_w if info.current_w > 0 else 1920
    desktop_h = info.current_h if info.current_h > 0 else 1080

    # Distinct initial window proportions calibrated by quality preset
    # Ensures low opens compact retro, balanced is medium, and high/ultra are wide & expansive
    quality_scales = {
        "1": 0.50, "low": 0.50,
        "2": 0.56, "retro": 0.56,
        "3": 0.62, "balanced": 0.62, "standard": 0.62,
        "4": 0.67, "classic": 0.67,
        "5": 0.72, "high": 0.72,
        "6": 0.77, "super": 0.77,
        "7": 0.82, "ultra": 0.82,
        "8": 0.88, "master": 0.88,
        "9": 0.92, "cinema": 0.92,
        "10": 0.93, "titan": 0.93,
        "11": 0.94, "overkill": 0.94,
        "12": 0.96, "godlike": 0.96,
        "13": 0.965, "monolith": 0.965,
        "14": 0.97, "singularity": 0.97,
        "15": 0.98, "infinite": 0.98,
    }
    active_quality = str(quality).lower() if quality else None
    if not active_quality or active_quality not in quality_scales:
        if cols <= 55:
            active_quality = "low"
        elif cols <= 70:
            active_quality = "retro"
        elif cols <= 85:
            active_quality = "balanced"
        elif cols <= 100:
            active_quality = "classic"
        elif cols <= 118:
            active_quality = "high"
        elif cols <= 132:
            active_quality = "super"
        elif cols <= 150:
            active_quality = "ultra"
        elif cols <= 170:
            active_quality = "master"
        elif cols <= 190:
            active_quality = "cinema"
        elif cols <= 215:
            active_quality = "titan"
        elif cols <= 245:
            active_quality = "overkill"
        elif cols <= 280:
            active_quality = "godlike"
        elif cols <= 320:
            active_quality = "monolith"
        elif cols <= 360:
            active_quality = "singularity"
        else:
            active_quality = "infinite"

    scale_ratio = quality_scales.get(active_quality, 0.65)
    max_avail_w = int(desktop_w * 0.96)
    max_avail_h = int(desktop_h * 0.90)

    box_w = max(420, min(max_avail_w, int(desktop_w * scale_ratio)))
    box_h = max(320, min(max_avail_h, int(desktop_h * scale_ratio * 0.92)))

    avail_content_w = max(100, box_w - gutter_w)
    avail_content_h = max(100, box_h - header_h - footer_h)

    # Compute target window dimensions preserving video aspect ratio
    vid_w = metadata.width if metadata.width > 0 else 16
    vid_h = metadata.height if metadata.height > 0 else 9
    aspect_ratio = vid_w / vid_h if vid_h > 0 else 1.7778

    if (avail_content_w / aspect_ratio) <= avail_content_h:
        content_w = avail_content_w
        content_h = int(avail_content_w / aspect_ratio)
    else:
        content_h = avail_content_h
        content_w = int(avail_content_h * aspect_ratio)

    win_w = max(420, content_w + gutter_w)
    win_h = max(320, content_h + header_h + footer_h)

    # Dynamic font scaling: test downwards from 48pt to 3pt to find crispest native monospace font
    rows = decoder.rows
    actual_avail_w = win_w - gutter_w
    actual_avail_h = win_h - header_h - footer_h
    target_cw = max(1, actual_avail_w // cols)
    target_ch = max(1, actual_avail_h // rows)
    actual_fs = 3
    for fs in range(48, 2, -1):
        test_font = pygame.font.SysFont("consolas", fs)
        tcw, tch = test_font.size("M")
        if tcw <= target_cw and tch <= target_ch:
            actual_fs = fs
            break

    # 4. Initialize UI Rendering Pipeline with screen-safe font size
    renderer = AsciiRenderer(
        font_name="consolas",
        font_size=actual_fs,
        char_ramp=chars,
        color_mode=color_mode,
    )

    # Ensure window is large enough to render the chosen font at 1:1 native resolution
    needed_w = cols * renderer.cw + gutter_w
    needed_h = rows * renderer.ch + header_h + footer_h
    win_w = min(max_avail_w, max(win_w, needed_w))
    win_h = min(max_avail_h, max(win_h, needed_h))

    # Set custom creepy eye icon BEFORE set_mode so Windows uses it for taskbar and titlebar
    icon_cand = get_resource_path(os.path.join("assets", "eye_icon.png"))
    if not os.path.exists(icon_cand):
        icon_cand = get_resource_path(os.path.join("assets", "icon.png"))
    if not os.path.exists(icon_cand):
        icon_cand = get_resource_path("eye_icon.png")
    if not os.path.exists(icon_cand):
        icon_cand = get_resource_path("icon.png")
    if os.path.exists(icon_cand):
        try:
            icon_surf = pygame.image.load(icon_cand)
            pygame.display.set_icon(icon_surf)
        except (pygame.error, OSError) as exc:
            logger.debug("Custom window icon could not be loaded: %s", exc)

    screen = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE)
    apply_windows_app_icon(screen)
    filename = os.path.basename(resolved_path)
    pygame.display.set_caption(filename)

    crt_effect = CrtEffect(width=win_w, height=win_h)
    hud_renderer = HudRenderer(font_name="consolas", font_size=max(12, font_size))
    hud_renderer.language = lang
    hud_renderer.seek_step = seek_step

    # 5. Playback State & Input Handling
    state = PlayerState(
        filename=filename,
        status="PLAYING",
        fps=target_fps,
        speed=1.0,
        zoom=1.0,
        current_time=0.0,
        duration=metadata.duration,
        crt_enabled=crt,
        loop=loop,
        show_help=False,
        show_hud=hud,
        has_audio=has_audio,
        audio_enabled=(audio and has_audio),
        color_mode=color_mode,
    )

    frame_gen = decoder.iter_frames()
    current_frame_data: tuple[float, any, any] | None = None
    try:
        current_frame_data = next(frame_gen)
    except StopIteration:
        current_frame_data = None

    def on_resize(w: int, h: int) -> None:
        nonlocal screen
        nw = max(320, w)
        nh = max(240, h)
        screen = pygame.display.set_mode((nw, nh), pygame.RESIZABLE)
        crt_effect.resize(nw, nh)

        # Fit the font to the resized window
        cur_gw = HudRenderer.GUTTER_WIDTH if getattr(state, "show_hud", False) else 0
        cur_hh = HudRenderer.HEADER_HEIGHT if getattr(state, "show_hud", False) else 0
        cur_fh = HudRenderer.STATUS_BAR_HEIGHT if getattr(state, "show_hud", False) else 0
        avail_w = max(40, nw - cur_gw)
        avail_h = max(40, nh - cur_hh - cur_fh)
        target_cw = max(1, avail_w // cols)
        target_ch = max(1, avail_h // rows)

        optimal_fs = 3
        for fs in range(48, 2, -1):
            tf = pygame.font.SysFont("consolas", fs)
            tcw, tch = tf.size("M")
            if tcw <= target_cw and tch <= target_ch:
                optimal_fs = fs
                break
        renderer.set_font_size(optimal_fs)

    def on_seek(target_time: float) -> None:
        nonlocal frame_gen, current_frame_data, virtual_clock, last_perf
        clamped_time = max(0.0, min(metadata.duration, target_time))
        virtual_clock = clamped_time
        last_perf = time.perf_counter()
        state.current_time = clamped_time
        decoder.seek(clamped_time)
        if audio_engine and has_audio:
            audio_engine.seek(clamped_time)
            if state.speed != 1.0:
                audio_engine.pause()
        frame_gen = decoder.iter_frames()
        try:
            current_frame_data = next(frame_gen)
        except StopIteration:
            current_frame_data = None

    input_handler = InputHandler(
        on_resize=on_resize,
        on_seek=on_seek,
        seek_step=seek_step,
    )

    def restart_stream() -> None:
        nonlocal frame_gen, current_frame_data, virtual_clock, last_perf
        decoder.seek(0.0)
        if audio_engine and has_audio:
            audio_engine.seek(0.0)
            audio_engine.play(0.0)
        virtual_clock = 0.0
        last_perf = time.perf_counter()
        state.current_time = 0.0
        frame_gen = decoder.iter_frames()
        try:
            current_frame_data = next(frame_gen)
        except StopIteration:
            current_frame_data = None

    # 6. Start Playback Clock & Audio
    if audio_engine and has_audio:
        audio_engine.play(0.0)

    clock = pygame.time.Clock()
    wall_start = time.perf_counter()
    last_perf = time.perf_counter()
    virtual_clock = 0.0

    # 7. Main Playback Loop
    try:
        while not input_handler.should_quit and state.status != "STOPPED":
            now = time.perf_counter()
            dt = min(0.066, max(0.0, now - last_perf))
            last_perf = now

            # Check runtime duration limit (for automated headless test runs)
            if max_duration is not None and (now - wall_start) >= max_duration:
                break

            # Handle Pygame user input events
            for event in pygame.event.get():
                action = input_handler.handle_event(event, state)
                if action == "TOGGLE_PLAY":
                    if state.status == "PAUSED":
                        if audio_engine and has_audio:
                            audio_engine.pause()
                    else:
                        virtual_clock = state.current_time
                        last_perf = time.perf_counter()
                        if audio_engine and has_audio and state.speed == 1.0:
                            audio_engine.resume()
                elif action in ("SPEED_UP", "SPEED_DOWN"):
                    virtual_clock = state.current_time
                    last_perf = time.perf_counter()
                    if state.speed != 1.0 and audio_engine and has_audio:
                        audio_engine.pause()
                    elif (
                        state.speed == 1.0
                        and audio_engine
                        and has_audio
                        and state.status == "PLAYING"
                    ):
                        audio_engine.seek(state.current_time)
                        audio_engine.resume()
                elif action == "CYCLE_SEEK":
                    hud_renderer.seek_step = input_handler.seek_step
                elif action == "TOGGLE_AUDIO":
                    if audio_engine and has_audio:
                        try:
                            pygame.mixer.music.set_volume(1.0 if state.audio_enabled else 0.0)
                        except (pygame.error, AttributeError):
                            pass
                elif action in ("SEEK_BACKWARD", "SEEK_FORWARD"):
                    pass  # Executed via on_seek callback
                elif action == "CYCLE_THEME":
                    renderer.set_color_mode(state.color_mode)
                elif action == "TOGGLE_FULLSCREEN":
                    is_fs = (screen.get_flags() & pygame.FULLSCREEN) != 0
                    if not is_fs:
                        screen = pygame.display.set_mode((desktop_w, desktop_h), pygame.FULLSCREEN | pygame.DOUBLEBUF)
                        on_resize(desktop_w, desktop_h)
                    else:
                        screen = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE)
                        on_resize(win_w, win_h)
                elif action == "QUIT":
                    break

            if input_handler.should_quit:
                break

            # Update Master Playback Clock
            if state.status == "PLAYING":
                if (
                    state.speed == 1.0
                    and audio_engine
                    and has_audio
                    and not audio_engine._is_paused
                    and (audio_engine.duration <= 0 or virtual_clock < audio_engine.duration)
                ):
                    master_time = audio_engine.get_master_time()
                    virtual_clock = master_time
                else:
                    virtual_clock += dt * state.speed
                    master_time = virtual_clock
                state.current_time = min(metadata.duration, master_time)
            else:
                master_time = state.current_time

            # Drop late frames and synchronize presentation
            if state.status == "PLAYING" and current_frame_data is not None:
                pts, _, _ = current_frame_data

                lag = master_time - pts
                # Drop stale frames to maintain synchronization without blocking
                max_drops = 2 if state.speed <= 1.0 else 3
                drop_count = 0
                while lag > frame_duration and drop_count < max_drops:
                    try:
                        current_frame_data = next(frame_gen)
                        pts, _, _ = current_frame_data
                        lag = master_time - pts
                        drop_count += 1
                    except StopIteration:
                        if state.loop:
                            restart_stream()
                        else:
                            current_frame_data = None
                        break

                # Prevent virtual clock from runaway drifting past achievable frame rate
                if current_frame_data is not None:
                    pts, _, _ = current_frame_data
                    if (master_time - pts) > 0.15:
                        virtual_clock = pts + 0.15
                        master_time = virtual_clock
                        state.current_time = min(metadata.duration, master_time)

            # Render Composited Frame on pure black canvas
            sw, sh = screen.get_size()
            screen.fill((0, 0, 0))

            # Viewport calculation (zero margin if show_hud is False)
            cur_gw = HudRenderer.GUTTER_WIDTH if getattr(state, "show_hud", False) else 0
            cur_hh = HudRenderer.HEADER_HEIGHT if getattr(state, "show_hud", False) else 0
            cur_fh = HudRenderer.STATUS_BAR_HEIGHT if getattr(state, "show_hud", False) else 0
            avail_w = max(0, sw - cur_gw)
            avail_h = max(0, sh - cur_hh - cur_fh)
            viewport_rect = pygame.Rect(cur_gw, cur_hh, avail_w, avail_h)

            if current_frame_data is not None:
                _, chars_to_render, colors_to_render = current_frame_data
                renderer.render_frame(
                    screen,
                    chars_to_render,
                    colors_to_render,
                    dest_rect=viewport_rect,
                )

            # Apply CRT scanlines, vignette, and phosphor bloom
            crt_effect.apply(screen, crt_enabled=state.crt_enabled)

            # Draw HUD chrome (Header, Coordinate Gutter, Status Bar, Help Modal)
            hud_renderer.draw_hud(
                screen,
                state,
                total_rows=rows,
                char_height=renderer.ch,
            )

            pygame.display.flip()
            clock.tick(60)
            state.fps = max(1.0, clock.get_fps())

            # Advance to next frame when current frame has been presented
            if state.status == "PLAYING" and current_frame_data is not None:
                pts, _, _ = current_frame_data
                if master_time >= pts:
                    try:
                        current_frame_data = next(frame_gen)
                    except StopIteration:
                        if state.loop:
                            restart_stream()
                        else:
                            current_frame_data = None

            # Fallback for loop if current_frame_data became None
            if current_frame_data is None and state.loop:
                restart_stream()

            # Detect clean termination at end-of-stream
            if (
                current_frame_data is None
                and not state.loop
                and state.current_time >= metadata.duration - 0.1
            ):
                state.status = "STOPPED"
                break

            # Prevent high CPU spinning while paused
            if state.status == "PAUSED":
                time.sleep(0.016)

    finally:
        if audio_engine is not None:
            audio_engine.stop()
        decoder.close()
        pygame.quit()

    return EXIT_SUCCESS


def main(argv: Sequence[str] | None = None) -> int:
    """
    CLI entry point for ascii_player.

    Args:
        argv: Command-line arguments sequence.

    Returns:
        Process exit code (0 for success, 1 for file error, 2 for format error).
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    cols = args.cols
    font_size = args.font_size
    chars = args.chars

    if args.quality:
        q_key = str(args.quality).strip().lower()
        if q_key in QUALITY_LOOKUP:
            q_cfg = QUALITY_LOOKUP[q_key]
            if args.cols == 80:
                cols = q_cfg["cols"]
            if args.font_size == 12:
                font_size = q_cfg["font_size"]
            if args.chars == DEFAULT_RAMP:
                chars = q_cfg["chars"]

    try:
        return play_video(
            video_path=args.input,
            cols=cols,
            fps=args.fps,
            chars=chars,
            crt=args.crt,
            font_size=font_size,
            lang=args.lang,
            headless=args.headless,
            char_aspect=args.aspect,
            loop=args.loop,
            max_duration=args.duration,
            audio=args.audio,
            quality=args.quality,
            color_mode=args.color_mode,
            seek_step=getattr(args, "seek_step", 5.0),
            hud=getattr(args, "hud", False),
        )
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return EXIT_FILE_NOT_FOUND
    except (ValueError, OSError) as exc:
        print(exc, file=sys.stderr)
        return EXIT_FORMAT_ERROR
    except KeyboardInterrupt:
        return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
