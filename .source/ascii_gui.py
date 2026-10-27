"""Desktop interface for video playback, rendering, and standalone export."""

from __future__ import annotations

import contextlib
import json
import os
import queue
import re
import subprocess
import sys
import threading

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

try:
    import pygame
except ImportError:
    print("[HATA / ERROR] Pygame kütüphanesi bulunamadı! Lütfen yükleyin: pip install pygame")
    sys.exit(1)


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


def open_folder_in_explorer(folder_path: str) -> None:
    """Safely open folder in Windows Explorer."""
    if os.environ.get("SDL_VIDEODRIVER") == "dummy" or os.environ.get("ASCII_TEST_MODE") == "1":
        return
    abs_folder = os.path.abspath(folder_path)
    os.makedirs(abs_folder, exist_ok=True)
    try:
        os.startfile(abs_folder)
    except (OSError, AttributeError):
        try:
            subprocess.Popen(["explorer.exe", abs_folder])
        except (OSError, subprocess.SubprocessError):
            pass



DEFAULT_RAMP = " .:-=+*#%@"
CLASSIC_16_RAMP = " .:-=+*#%@#%&WM"
DETAILED_RAMP = " .'`^\",:;Il!i~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
EXTENDED_92_RAMP = " `.`-':_\",^=;><+!rc*/z?sLTv)J7(|Fi{C}fI31tlu[neoZ5Yxjya]2ESwqkP6h9d4VpOGbUAKXHm8RD#$Bg0MNWQ%&@"

# Quality presets
QUALITY_PRESETS = [
    {
        "id": "low",
        "name": "1. LOW",
        "cols": 50,
        "desc": "50 sütun, kısa karakter dizisi.",
        "tag": "50 sütun • 10 karakter",
        "chars": DEFAULT_RAMP,
    },
    {
        "id": "retro",
        "name": "2. RETRO",
        "cols": 65,
        "desc": "65 sütun, kısa karakter dizisi.",
        "tag": "65 sütun • 10 karakter",
        "chars": DEFAULT_RAMP,
    },
    {
        "id": "balanced",
        "name": "3. BALANCED",
        "cols": 80,
        "desc": "80 sütun, klasik karakter dizisi.",
        "tag": "80 sütun • 15 karakter",
        "chars": CLASSIC_16_RAMP,
    },
    {
        "id": "classic",
        "name": "4. CLASSIC",
        "cols": 95,
        "desc": "95 sütun, klasik karakter dizisi.",
        "tag": "95 sütun • 15 karakter",
        "chars": CLASSIC_16_RAMP,
    },
    {
        "id": "high",
        "name": "5. HIGH",
        "cols": 110,
        "desc": "110 sütun, detaylı karakter dizisi.",
        "tag": "110 sütun • 68 karakter",
        "chars": DETAILED_RAMP,
    },
    {
        "id": "super",
        "name": "6. SUPER",
        "cols": 125,
        "desc": "125 sütun, detaylı karakter dizisi.",
        "tag": "125 sütun • 68 karakter",
        "chars": DETAILED_RAMP,
    },
    {
        "id": "ultra",
        "name": "7. ULTRA",
        "cols": 140,
        "desc": "140 sütun, detaylı karakter dizisi.",
        "tag": "140 sütun • 68 karakter",
        "chars": DETAILED_RAMP,
    },
    {
        "id": "master",
        "name": "8. MASTER",
        "cols": 160,
        "desc": "160 sütun, detaylı karakter dizisi.",
        "tag": "160 sütun • 68 karakter",
        "chars": DETAILED_RAMP,
    },
    {
        "id": "cinema",
        "name": "9. CINEMA",
        "cols": 180,
        "desc": "180 sütun, detaylı karakter dizisi.",
        "tag": "180 sütun • 68 karakter",
        "chars": DETAILED_RAMP,
    },
    {
        "id": "titan",
        "name": "10. TITAN",
        "cols": 200,
        "desc": "200 sütun, detaylı karakter dizisi.",
        "tag": "200 sütun • 68 karakter",
        "chars": DETAILED_RAMP,
    },
    {
        "id": "overkill",
        "name": "11. OVERKILL",
        "cols": 230,
        "desc": "230 sütun, detaylı karakter dizisi.",
        "tag": "230 sütun • 68 karakter",
        "chars": DETAILED_RAMP,
    },
    {
        "id": "godlike",
        "name": "12. GODLIKE",
        "cols": 260,
        "desc": "260 sütun, genişletilmiş karakter dizisi.",
        "tag": "260 sütun • 94 karakter",
        "chars": EXTENDED_92_RAMP,
    },
    {
        "id": "monolith",
        "name": "13. MONOLITH",
        "cols": 300,
        "desc": "300 sütun, genişletilmiş karakter dizisi.",
        "tag": "300 sütun • 94 karakter",
        "chars": EXTENDED_92_RAMP,
    },
    {
        "id": "singularity",
        "name": "14. SINGULARITY",
        "cols": 340,
        "desc": "340 sütun, genişletilmiş karakter dizisi.",
        "tag": "340 sütun • 94 karakter",
        "chars": EXTENDED_92_RAMP,
    },
    {
        "id": "infinite",
        "name": "15. INFINITE",
        "cols": 380,
        "desc": "380 sütun, genişletilmiş karakter dizisi.",
        "tag": "380 sütun • 94 karakter",
        "chars": EXTENDED_92_RAMP,
    },
]

# 5 Retro Color Themes / Palettes
COLOR_THEMES = [
    {
        "id": "truecolor",
        "name": "Truecolor RGB",
        "desc": "Orijinal 24-bit tam renkli canlı görüntü (RGB)",
        "color": (235, 240, 245),
        "tag": "24-Bit RGB",
    },
    {
        "id": "grayscale",
        "name": "Siyah-Beyaz",
        "desc": "Klasik monokrom parlaklık ve gri tonlama",
        "color": (200, 200, 200),
        "tag": "Monochrome",
    },
    {
        "id": "green",
        "name": "Matrix Yeşili",
        "desc": "Retro yeşil fosforlu CRT terminal efekti (#00FF66)",
        "color": (0, 255, 102),
        "tag": "Green #00FF66",
    },
    {
        "id": "amber",
        "name": "Amber Terminali",
        "desc": "Klasik vintage amber / kehribar terminal (#FFB000)",
        "color": (255, 176, 0),
        "tag": "Amber #FFB000",
    },
    {
        "id": "cyberpunk",
        "name": "Cyberpunk Neon",
        "desc": "Neon camgöbeği & fuşya pembe sentetik renk paleti",
        "color": (240, 70, 255),
        "tag": "Cyan / Pink",
    },
]

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

VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv")


def get_resource_path(relative_path: str) -> str:
    """Resolve asset path dynamically for development and PyInstaller bundles."""
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


def scan_videos(root_dir: str = ".") -> list[dict]:
    """Scan directory for video files and return metadata list."""
    videos = []
    try:
        entries = sorted(os.listdir(root_dir))
    except OSError:
        return videos

    for entry in entries:
        full_path = os.path.join(root_dir, entry)
        if os.path.isfile(full_path):
            ext = os.path.splitext(entry)[1].lower()
            if ext in VIDEO_EXTS:
                size_bytes = os.path.getsize(full_path)
                if size_bytes >= 1024 * 1024:
                    size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
                else:
                    size_str = f"{size_bytes / 1024:.1f} KB"
                videos.append({
                    "name": entry,
                    "path": full_path,
                    "size_str": size_str,
                })
    return videos


class AsciiStudioGui:
    """Retro Cyber-Terminal GUI Studio & Launcher."""

    # Color Palette
    COLOR_BG = (12, 14, 20)
    COLOR_PANEL_BG = (18, 22, 32)
    COLOR_PANEL_HOVER = (28, 36, 54)
    COLOR_PANEL_ACTIVE = (36, 48, 76)
    COLOR_BORDER = (45, 55, 78)
    COLOR_BORDER_FOCUS = (85, 230, 120)
    COLOR_BORDER_HOVER = (56, 189, 248)

    COLOR_AMBER = (245, 175, 55)
    COLOR_GREEN = (85, 230, 120)
    COLOR_CYAN = (56, 189, 248)
    COLOR_WHITE = (235, 240, 245)
    COLOR_STEEL = (165, 175, 190)
    COLOR_MUTED = (95, 105, 120)
    COLOR_RED = (240, 80, 80)

    def __init__(self, width: int = 1024, height: int = 740) -> None:
        pygame.init()
        pygame.font.init()

        os.environ["SDL_VIDEO_CENTERED"] = "1"
        self.width = width
        self.height = height

        if (
            os.environ.get("SDL_VIDEODRIVER") != "dummy"
            and not os.environ.get("ASCII_TEST_MODE")
            and hasattr(pygame.display, "get_desktop_sizes")
            and pygame.display.get_desktop_sizes()
        ):
            desk_w, desk_h = pygame.display.get_desktop_sizes()[0]
            if desk_w > 0 and desk_h > 0:
                max_w = max(800, desk_w - 40)
                max_h = max(600, desk_h - 80)
                self.width = min(self.width, max_w)
                self.height = min(self.height, max_h)

        # Load eerie eye icon BEFORE set_mode so Windows uses it for taskbar and titlebar
        icon_path = get_resource_path(os.path.join("assets", "eye_icon.png"))
        if not os.path.exists(icon_path):
            icon_path = get_resource_path(os.path.join("assets", "icon.png"))
        if not os.path.exists(icon_path):
            icon_path = get_resource_path("eye_icon.png")
        if not os.path.exists(icon_path):
            icon_path = get_resource_path("icon.png")

        if os.path.exists(icon_path):
            try:
                self.icon_surf = pygame.image.load(icon_path)
                pygame.display.set_icon(self.icon_surf)
            except (pygame.error, OSError):
                self.icon_surf = None
        else:
            self.icon_surf = None

        self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
        apply_windows_app_icon(self.screen)
        pygame.display.set_caption("RETRO ASCII VIDEO STUDIO")

        # Fonts
        self.font_big_pct = pygame.font.SysFont("consolas", 26, bold=True)
        self.font_title = pygame.font.SysFont("consolas", 18, bold=True)
        self.font_header = pygame.font.SysFont("consolas", 13, bold=True)
        self.font_main = pygame.font.SysFont("consolas", 12)
        self.font_small = pygame.font.SysFont("consolas", 10)

        # State
        self.videos = scan_videos(".")
        self.selected_video_idx = 0 if self.videos else -1
        self.selected_quality_idx = 2  # Default to 3. BALANCED (Standart)
        self.crt_enabled = False
        self.audio_enabled = True
        self.loop_enabled = False
        self.clean_bg_enabled = True  # Default: Pure black background (clean sharp characters, no muddy bleed)
        self.SEEK_STEPS = [5, 10, 30, 60]
        self.seek_step_idx = 0
        self.seek_step = 5.0
        self.color_themes = COLOR_THEMES
        self.selected_color_theme_idx = 0  # Default to Truecolor RGB
        self.selected_color_idx = 0
        self.render_resolutions = RENDER_RESOLUTIONS
        self.selected_resolution_idx = 0  # Default: Auto 1080p / 2K

        # Scrolling state
        self.video_scroll_y = 0
        self.quality_scroll_y = 0

        # Exact clickable regions registered each frame
        self.rendered_video_rects: list[tuple[int, pygame.Rect]] = []
        self.rendered_quality_rects: list[tuple[int, pygame.Rect]] = []
        self.rendered_buttons: dict[str, pygame.Rect] = {}
        self.modal_buttons: dict[str, pygame.Rect] = {}

        self.hovered_video_idx = -1
        self.hovered_quality_idx = -1

        self.status_message = "Hazır / Ready"
        self.status_color = self.COLOR_GREEN

        # Live Progress & Worker Thread State
        self.progress_queue: queue.Queue = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.is_busy: bool = False
        self.active_task: str | None = None  # "render" or "export"
        self.active_video_name: str = ""
        self.active_target_folder: str = ""

        self.progress_pct: float = 0.0
        self.progress_current: int = 0
        self.progress_total: int = 0
        self.progress_fps: float = 0.0
        self.progress_eta: float = 0.0
        self.progress_bar_text: str = "[░░░░░░░░░░░░░░░░░░░░] 0.0%"
        self.progress_stage: str = "Hazır"

        # Completion Modal State
        self.show_completion_modal: bool = False
        self.completion_success: bool = True
        self.completion_message: str = ""
        self.completion_folder: str = ""

        # Internal Drag-and-drop Video State
        self.dragging_video_idx: int = -1
        self.drag_start_pos: tuple[int, int] = (0, 0)
        self.is_dragging_video: bool = False

        self.clock = pygame.time.Clock()

    def run(self) -> None:
        """Main event and rendering loop."""
        running = True
        while running:
            self.clock.tick(60)

            # 1. Process asynchronous worker events
            self.poll_worker_queue()

            # 2. Event Handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE:
                    self.width, self.height = max(800, event.w), max(600, event.h)
                    self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
                elif event.type == pygame.DROPFILE:
                    self.handle_drop_file(event.file)
                elif event.type == pygame.MOUSEMOTION:
                    self.handle_mouse_move(event.pos)
                elif event.type == pygame.MOUSEWHEEL:
                    self.handle_scroll(event.x, event.y)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                    self.handle_click(event.pos, button=event.button)
                elif event.type == pygame.MOUSEBUTTONUP and event.button in (1, 3):
                    self.handle_mouse_up(event.pos)
                elif event.type == pygame.KEYDOWN:
                    if self.show_completion_modal and not self.is_busy:
                        if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                            self.show_completion_modal = False
                    elif self.is_busy:
                        pass
                    else:
                        if event.key in (pygame.K_ESCAPE, pygame.K_q):
                            running = False
                        elif event.key == pygame.K_UP:
                            if self.videos:
                                self.selected_video_idx = (self.selected_video_idx - 1) % len(self.videos)
                                self.ensure_video_visible(self.selected_video_idx)
                        elif event.key == pygame.K_DOWN:
                            if self.videos:
                                self.selected_video_idx = (self.selected_video_idx + 1) % len(self.videos)
                                self.ensure_video_visible(self.selected_video_idx)
                        elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9):
                            num = event.key - pygame.K_1
                            if 0 <= num < len(QUALITY_PRESETS):
                                self.selected_quality_idx = num
                                self.ensure_quality_visible(num)
                        elif event.key == pygame.K_0:
                            if len(QUALITY_PRESETS) >= 10:
                                self.selected_quality_idx = 9
                                self.ensure_quality_visible(9)
                        elif event.key in (pygame.K_RIGHTBRACKET, pygame.K_PLUS, pygame.K_KP_PLUS):
                            self.selected_quality_idx = (self.selected_quality_idx + 1) % len(QUALITY_PRESETS)
                            self.ensure_quality_visible(self.selected_quality_idx)
                        elif event.key in (pygame.K_LEFTBRACKET, pygame.K_MINUS, pygame.K_KP_MINUS):
                            self.selected_quality_idx = (self.selected_quality_idx - 1) % len(QUALITY_PRESETS)
                            self.ensure_quality_visible(self.selected_quality_idx)
                        elif event.key == pygame.K_t:
                            self.cycle_color_theme()
                        elif event.key == pygame.K_r:
                            self.refresh_videos()
                        elif event.key == pygame.K_c:
                            self.crt_enabled = not self.crt_enabled
                        elif event.key in (pygame.K_s, pygame.K_a):
                            self.audio_enabled = not self.audio_enabled
                        elif event.key == pygame.K_l:
                            self.loop_enabled = not self.loop_enabled
                        elif event.key == pygame.K_RETURN:
                            self.launch_player()
                        elif event.key in (pygame.K_x, pygame.K_m):
                            self.launch_renderer()
                        elif event.key == pygame.K_b:
                            self.clean_bg_enabled = not self.clean_bg_enabled
                            mode_str = "Siyah arka plan" if self.clean_bg_enabled else "Renkli arka plan"
                            self.status_message = f"Karakter Arka Planı: {mode_str}"
                            self.status_color = self.COLOR_GREEN if self.clean_bg_enabled else self.COLOR_AMBER
                        elif event.key == pygame.K_z:
                            self.cycle_seek_step()
                        elif event.key in (pygame.K_v, pygame.K_k):
                            self.cycle_render_resolution()
                        elif event.key == pygame.K_e:
                            self.launch_exporter()

            # 3. Render
            self.draw()
            pygame.display.flip()

        pygame.quit()

    def refresh_videos(self) -> None:
        """Rescan directory for new media files."""
        self.videos = scan_videos(".")
        if self.selected_video_idx >= len(self.videos):
            self.selected_video_idx = len(self.videos) - 1
        self.status_message = f"Tazelendi: {len(self.videos)} video dosyası bulundu"
        self.status_color = self.COLOR_CYAN

    def get_video_list_rect(self) -> pygame.Rect:
        """Exact clipping viewport rectangle for scrollable video items."""
        panel_top = 48
        panel_bottom = self.height - 54
        panel_h = max(200, panel_bottom - panel_top)
        panel_w = (self.width - 50) // 2
        return pygame.Rect(26, panel_top + 26, panel_w - 12, panel_h - 32)

    def ensure_video_visible(self, idx: int) -> None:
        """Auto-scroll video panel to make selected item visible."""
        v_rect = self.get_video_list_rect()
        viewport_h = v_rect.height
        item_stride = 37
        item_h = 34
        item_top = idx * item_stride
        item_bottom = item_top + item_h
        total_h = len(self.videos) * item_stride
        max_scroll = max(0, total_h - viewport_h)

        if item_top < self.video_scroll_y:
            self.video_scroll_y = item_top
        elif item_bottom > self.video_scroll_y + viewport_h:
            self.video_scroll_y = min(max_scroll, item_bottom - viewport_h)

    def cycle_color_theme(self) -> None:
        """Cycle through available retro color themes."""
        self.selected_color_theme_idx = (self.selected_color_theme_idx + 1) % len(self.color_themes)
        self.selected_color_idx = self.selected_color_theme_idx
        theme = self.color_themes[self.selected_color_theme_idx]
        self.status_message = f"Renk Teması: {theme['name']} ({theme['tag']})"
        self.status_color = theme["color"]

    def cycle_color_theme_reverse(self) -> None:
        """Cycle backward through available retro color themes."""
        self.selected_color_theme_idx = (self.selected_color_theme_idx - 1) % len(self.color_themes)
        self.selected_color_idx = self.selected_color_theme_idx
        theme = self.color_themes[self.selected_color_theme_idx]
        self.status_message = f"Renk Teması: {theme['name']} ({theme['tag']})"
        self.status_color = theme["color"]

    def cycle_seek_step(self) -> None:
        """Cycle seeking jump interval (5s -> 10s -> 30s -> 60s)."""
        self.seek_step_idx = (self.seek_step_idx + 1) % len(self.SEEK_STEPS)
        self.seek_step = float(self.SEEK_STEPS[self.seek_step_idx])
        self.status_message = f"Hızlı Sarma Adımı: ±{int(self.seek_step)} saniye [Z]"
        self.status_color = self.COLOR_CYAN

    def cycle_seek_step_reverse(self) -> None:
        """Cycle seeking jump interval backward (60s -> 30s -> 10s -> 5s)."""
        self.seek_step_idx = (self.seek_step_idx - 1) % len(self.SEEK_STEPS)
        self.seek_step = float(self.SEEK_STEPS[self.seek_step_idx])
        self.status_message = f"Hızlı Sarma Adımı: ±{int(self.seek_step)} saniye [Z]"
        self.status_color = self.COLOR_CYAN

    def cycle_render_resolution(self) -> None:
        """Cycle target render resolution (Auto -> 1080p -> 2K -> 4K -> 720p -> Original)."""
        self.selected_resolution_idx = (self.selected_resolution_idx + 1) % len(self.render_resolutions)
        res = self.render_resolutions[self.selected_resolution_idx]
        self.status_message = f"Render Çözünürlüğü: {res['name']} [{res['tag']}] [V]"
        self.status_color = self.COLOR_CYAN

    def cycle_render_resolution_reverse(self) -> None:
        """Cycle target render resolution backward (Original -> 720p -> 4K -> 2K -> 1080p -> Auto)."""
        self.selected_resolution_idx = (self.selected_resolution_idx - 1) % len(self.render_resolutions)
        res = self.render_resolutions[self.selected_resolution_idx]
        self.status_message = f"Render Çözünürlüğü: {res['name']} [{res['tag']}] [V]"
        self.status_color = self.COLOR_CYAN

    def get_settings_height(self) -> int:
        """Total height of settings panel at bottom of right panel."""
        return 176

    def get_quality_list_rect(self) -> pygame.Rect:
        """Exact clipping viewport rectangle for scrollable quality presets."""
        panel_w = (self.width - 50) // 2
        right_x = panel_w + 30
        right_w = self.width - right_x - 20
        panel_top = 48
        panel_bottom = self.height - 54
        panel_h = max(200, panel_bottom - panel_top)
        settings_h = self.get_settings_height()
        top_y = panel_top + 22
        bottom_y = panel_top + panel_h - settings_h - 2
        h = max(60, bottom_y - top_y)
        return pygame.Rect(right_x + 8, top_y, right_w - 16, h)

    def ensure_quality_visible(self, idx: int) -> None:
        """Auto-scroll quality presets panel to make selected preset fully visible."""
        q_rect = self.get_quality_list_rect()
        viewport_h = q_rect.height
        total_h = len(QUALITY_PRESETS) * 29
        max_scroll = max(0, total_h - viewport_h)

        item_top = idx * 29
        item_bottom = item_top + 28

        if item_top < self.quality_scroll_y:
            self.quality_scroll_y = item_top
        elif item_bottom > self.quality_scroll_y + viewport_h:
            self.quality_scroll_y = min(max_scroll, item_bottom - viewport_h)

    def handle_scroll(self, sx: int, sy: int) -> None:
        """Handle mouse wheel scrolling on left and right panels."""
        mx, _ = pygame.mouse.get_pos()
        panel_w = (self.width - 50) // 2
        scroll_amount = sy * 29

        if mx < panel_w + 30:
            # Video panel scroll
            v_rect = self.get_video_list_rect()
            viewport_h = v_rect.height
            total_h = len(self.videos) * 37
            max_scroll = max(0, total_h - viewport_h)
            self.video_scroll_y = max(0, min(max_scroll, self.video_scroll_y - scroll_amount))
        else:
            # Quality panel scroll
            q_rect = self.get_quality_list_rect()
            viewport_h = q_rect.height
            total_h = len(QUALITY_PRESETS) * 29
            max_scroll = max(0, total_h - viewport_h)
            self.quality_scroll_y = max(0, min(max_scroll, self.quality_scroll_y - scroll_amount))

    def handle_mouse_move(self, pos: tuple[int, int]) -> None:
        """Update hover state using exact collision detection and track internal drag gestures."""
        if self.dragging_video_idx >= 0 and not self.is_busy:
            dx = pos[0] - self.drag_start_pos[0]
            dy = pos[1] - self.drag_start_pos[1]
            if (dx * dx + dy * dy) >= 36:
                self.is_dragging_video = True

        self.hovered_video_idx = -1
        self.hovered_quality_idx = -1

        for idx, rect in self.rendered_video_rects:
            if rect.collidepoint(pos):
                self.hovered_video_idx = idx
                break

        for idx, rect in self.rendered_quality_rects:
            if rect.collidepoint(pos):
                self.hovered_quality_idx = idx
                break

    def handle_mouse_up(self, pos: tuple[int, int]) -> None:
        """Handle mouse button release for drag-and-drop onto action buttons."""
        if self.is_dragging_video and self.dragging_video_idx >= 0 and not self.is_busy:
            target_idx = self.dragging_video_idx
            if self.rendered_buttons.get("EXPORT", pygame.Rect(0, 0, 0, 0)).collidepoint(pos):
                self.selected_video_idx = target_idx
                self.ensure_video_visible(target_idx)
                self.launch_exporter()
            elif self.rendered_buttons.get("RENDER", pygame.Rect(0, 0, 0, 0)).collidepoint(pos):
                self.selected_video_idx = target_idx
                self.ensure_video_visible(target_idx)
                self.launch_renderer()
            elif self.rendered_buttons.get("PLAY", pygame.Rect(0, 0, 0, 0)).collidepoint(pos):
                self.selected_video_idx = target_idx
                self.ensure_video_visible(target_idx)
                self.launch_player()

        self.dragging_video_idx = -1
        self.is_dragging_video = False

    def handle_drop_file(self, dropped_path: str) -> None:
        """Handle drag-and-dropped video file onto the GUI window."""
        if self.is_busy:
            return
        if not os.path.isfile(dropped_path):
            return
        ext = os.path.splitext(dropped_path)[1].lower()
        if ext not in VIDEO_EXTS:
            self.status_message = f"[UYARI] Desteklenmeyen video dosyası: {ext}"
            self.status_color = self.COLOR_RED
            return

        # Find or add to self.videos
        found_idx = -1
        for idx, v in enumerate(self.videos):
            if os.path.abspath(v["path"]) == os.path.abspath(dropped_path):
                found_idx = idx
                break

        if found_idx == -1:
            size_bytes = os.path.getsize(dropped_path)
            if size_bytes >= 1024 * 1024:
                size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
            else:
                size_str = f"{size_bytes / 1024:.1f} KB"
            self.videos.insert(0, {
                "name": os.path.basename(dropped_path),
                "path": os.path.abspath(dropped_path),
                "size_str": size_str,
            })
            found_idx = 0

        self.selected_video_idx = found_idx
        self.ensure_video_visible(found_idx)

        # Check if dropped directly onto RENDER, EXPORT or PLAY button
        m_pos = pygame.mouse.get_pos()
        if self.rendered_buttons.get("RENDER", pygame.Rect(0, 0, 0, 0)).collidepoint(m_pos):
            self.launch_renderer()
        elif self.rendered_buttons.get("EXPORT", pygame.Rect(0, 0, 0, 0)).collidepoint(m_pos):
            self.launch_exporter()
        elif self.rendered_buttons.get("PLAY", pygame.Rect(0, 0, 0, 0)).collidepoint(m_pos):
            self.launch_player()
        else:
            self.status_message = f"Seçildi: {os.path.basename(dropped_path)} (İşlem için RENDER AL veya EXE seçin / sürükleyin)"
            self.status_color = self.COLOR_GREEN

    def handle_click(self, pos: tuple[int, int], button: int = 1) -> None:
        """Exact collision click detection for all UI elements (supports left click 1 and right click 3)."""
        if self.show_completion_modal and not self.is_busy:
            if self.modal_buttons.get("OPEN_FOLDER", pygame.Rect(0, 0, 0, 0)).collidepoint(pos):
                if self.completion_folder:
                    open_folder_in_explorer(self.completion_folder)
                return
            if self.modal_buttons.get("CLOSE_MODAL", pygame.Rect(0, 0, 0, 0)).collidepoint(pos):
                self.show_completion_modal = False
                return
            # Click outside modal dialog dismisses it
            sw, sh = self.width, self.height
            mw = min(660, sw - 40)
            mh = 270
            modal_rect = pygame.Rect((sw - mw) // 2, (sh - mh) // 2, mw, mh)
            if not modal_rect.collidepoint(pos):
                self.show_completion_modal = False
            return

        if self.is_busy:
            return

        # 1. Video selection & drag gesture start (left-click only starts drag)
        for idx, rect in self.rendered_video_rects:
            if rect.collidepoint(pos):
                self.selected_video_idx = idx
                if button == 1:
                    self.dragging_video_idx = idx
                    self.drag_start_pos = pos
                    self.is_dragging_video = False
                return

        # 2. Quality selection (left click selects; right click on active preset reverse cycles)
        for idx, rect in self.rendered_quality_rects:
            if rect.collidepoint(pos):
                if button == 3 and idx == self.selected_quality_idx:
                    self.selected_quality_idx = (self.selected_quality_idx - 1) % len(QUALITY_PRESETS)
                else:
                    self.selected_quality_idx = idx
                self.ensure_quality_visible(self.selected_quality_idx)
                preset = QUALITY_PRESETS[self.selected_quality_idx]
                self.status_message = f"Kalite Seviyesi: {preset['name']} [{preset['tag']}]"
                self.status_color = self.COLOR_CYAN
                return

        # 3. Buttons & Toggles (Left click cycles forward, Right click cycles backward or toggles)
        for btn_name, rect in self.rendered_buttons.items():
            if rect.collidepoint(pos):
                if btn_name == "HEADER_QUALITY":
                    if button == 3:
                        self.selected_quality_idx = (self.selected_quality_idx - 1) % len(QUALITY_PRESETS)
                    else:
                        self.selected_quality_idx = (self.selected_quality_idx + 1) % len(QUALITY_PRESETS)
                    self.ensure_quality_visible(self.selected_quality_idx)
                    preset = QUALITY_PRESETS[self.selected_quality_idx]
                    self.status_message = f"Kalite Seviyesi: {preset['name']} [{preset['tag']}]"
                    self.status_color = self.COLOR_CYAN
                if btn_name == "REFRESH":
                    self.refresh_videos()
                elif btn_name == "TOGGLE_CRT":
                    self.crt_enabled = not self.crt_enabled
                elif btn_name == "TOGGLE_AUDIO":
                    self.audio_enabled = not self.audio_enabled
                elif btn_name == "TOGGLE_LOOP":
                    self.loop_enabled = not self.loop_enabled
                elif btn_name == "TOGGLE_COLOR":
                    if button == 3:
                        self.cycle_color_theme_reverse()
                    else:
                        self.cycle_color_theme()
                elif btn_name == "TOGGLE_SEEK":
                    if button == 3:
                        self.cycle_seek_step_reverse()
                    else:
                        self.cycle_seek_step()
                elif btn_name == "TOGGLE_BG":
                    self.clean_bg_enabled = not self.clean_bg_enabled
                    mode_str = "Siyah arka plan" if self.clean_bg_enabled else "Renkli arka plan"
                    self.status_message = f"Karakter Arka Planı: {mode_str}"
                    self.status_color = self.COLOR_GREEN if self.clean_bg_enabled else self.COLOR_AMBER
                elif btn_name == "TOGGLE_RESOLUTION":
                    if button == 3:
                        self.cycle_render_resolution_reverse()
                    else:
                        self.cycle_render_resolution()
                elif btn_name == "PLAY":
                    self.launch_player()
                elif btn_name == "RENDER":
                    self.launch_renderer()
                elif btn_name == "EXPORT":
                    self.launch_exporter()
                elif btn_name == "QUIT":
                    pygame.event.post(pygame.event.Event(pygame.QUIT))
                return

    def _run_subprocess_worker(self, cmd: list[str], target_folder: str, task_name: str) -> None:
        """Worker thread executing subprocess with real-time JSON progress capture."""
        try:
            popen_kwargs: dict = {}
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
                **popen_kwargs,
            )
            sub_done_data: dict | None = None
            if proc.stdout is not None:
                for raw_line in proc.stdout:
                    line = raw_line.strip()
                    if not line:
                        continue
                    if "__PROGRESS_JSON__" in line:
                        try:
                            json_str = line.split("__PROGRESS_JSON__", 1)[1]
                            data = json.loads(json_str)
                            m_type = data.get("type", "progress")
                            if m_type == "done":
                                sub_done_data = data
                            else:
                                self.progress_queue.put((m_type, data))
                        except (json.JSONDecodeError, ValueError):
                            pass
                    else:
                        self.progress_queue.put(("log", line))
                proc.stdout.close()

            proc.wait()
            success = (proc.returncode == 0) and (sub_done_data is None or sub_done_data.get("success", True))
            err_msg = ""
            if sub_done_data and not sub_done_data.get("success", True):
                err_msg = sub_done_data.get("error", "")
            resolved_folder = target_folder
            if sub_done_data and "folder" in sub_done_data:
                resolved_folder = sub_done_data["folder"]

            self.progress_queue.put(("done", {
                "success": success,
                "returncode": proc.returncode,
                "target_folder": resolved_folder,
                "task": task_name,
                "error": err_msg,
            }))
        except (OSError, subprocess.SubprocessError) as exc:
            self.progress_queue.put(("error", str(exc)))

    def poll_worker_queue(self) -> None:
        """Poll progress queue from worker thread and update UI state."""
        while not self.progress_queue.empty():
            try:
                msg_type, payload = self.progress_queue.get_nowait()
            except queue.Empty:
                break

            if msg_type == "progress":
                self.progress_pct = payload.get("pct", self.progress_pct)
                self.progress_current = payload.get("current", self.progress_current)
                self.progress_total = payload.get("total", self.progress_total)
                self.progress_fps = payload.get("fps", self.progress_fps)
                self.progress_eta = payload.get("eta", self.progress_eta)
                if "text" in payload:
                    self.progress_bar_text = payload["text"]
                if "stage" in payload:
                    self.progress_stage = payload["stage"]
                self.status_message = self.progress_bar_text
                self.status_color = self.COLOR_CYAN

            elif msg_type == "log":
                if any(k in payload for k in ("PyInstaller", "Kare", "NPZ", "audio", "WAV", "Render")):
                    self.progress_stage = payload[:85]

            elif msg_type == "done":
                self.is_busy = False
                success = payload.get("success", False)
                folder = payload.get("target_folder", self.active_target_folder)
                self.show_completion_modal = True
                self.completion_success = success
                self.completion_folder = folder

                if success:
                    self.progress_pct = 100.0
                    task_title = "Video Render" if self.active_task == "render" else "EXE projesi"
                    self.completion_message = f"{task_title} başarıyla oluşturuldu!\nKlasör: {folder}"
                    self.status_message = f"[BAŞARILI] {folder} klasörüne kaydedildi!"
                    self.status_color = self.COLOR_GREEN
                    # Open folder automatically in Windows Explorer
                    open_folder_in_explorer(folder)
                else:
                    rc = payload.get("returncode", -1)
                    err = payload.get("error")
                    if err:
                        self.completion_message = f"Hata: {err}"
                    else:
                        self.completion_message = f"İşlem başarısız oldu (Hata Kodu: {rc})"
                    self.status_message = f"[HATA] {self.completion_message}"
                    self.status_color = self.COLOR_RED

            elif msg_type == "error":
                self.is_busy = False
                self.show_completion_modal = True
                self.completion_success = False
                self.completion_message = f"Beklenmedik Hata: {payload}"
                self.status_message = f"[HATA] {payload}"
                self.status_color = self.COLOR_RED

    def launch_player(self) -> None:
        """Launch live ASCII video player with chosen settings."""
        if not self.videos or self.selected_video_idx < 0:
            self.status_message = "[UYARI] Önce bir video dosyası seçmelisiniz!"
            self.status_color = self.COLOR_RED
            return

        video = self.videos[self.selected_video_idx]
        preset = QUALITY_PRESETS[self.selected_quality_idx]

        self.status_message = f"Oynatıcı Başlatılıyor: {video['name']} ({preset['id']})..."
        self.status_color = self.COLOR_GREEN
        self.draw()
        pygame.display.flip()

        py_exec = sys.executable
        if sys.platform == "win32":
            pyw_cand = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if os.path.exists(pyw_cand):
                py_exec = pyw_cand

        color_mode_id = self.color_themes[self.selected_color_theme_idx]["id"]
        cmd = [
            py_exec,
            "ascii_player.py",
            "-i", video["path"],
            "--quality", preset["id"],
            "--color-mode", color_mode_id,
        ]
        if self.crt_enabled:
            cmd.append("--crt")
        else:
            cmd.append("--no-crt")
        if self.audio_enabled:
            cmd.append("--audio")
        else:
            cmd.append("--no-audio")
        if self.loop_enabled:
            cmd.append("--loop")
        else:
            cmd.append("--no-loop")
        cmd.extend(["--seek-step", str(self.seek_step)])

        popen_kwargs: dict = {}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            subprocess.Popen(cmd, **popen_kwargs)
            self.status_message = f"Oynatılıyor: {video['name']} ({preset['name']}, {color_mode_id})"
            self.status_color = self.COLOR_GREEN
        except (subprocess.SubprocessError, OSError) as exc:
            self.status_message = f"[HATA] Oynatıcı başlatılamadı: {exc}"
            self.status_color = self.COLOR_RED

    def launch_renderer(self) -> None:
        """Launch MP4 Video Renderer with real-time percentage progress bar."""
        if self.is_busy:
            return
        if not self.videos or self.selected_video_idx < 0:
            self.status_message = "[UYARI] Önce bir video dosyası seçmelisiniz!"
            self.status_color = self.COLOR_RED
            return

        video = self.videos[self.selected_video_idx]
        preset = QUALITY_PRESETS[self.selected_quality_idx]
        color_mode_id = self.color_themes[self.selected_color_theme_idx]["id"]
        out_folder = get_video_output_dir(video["path"], "output")
        folder_stem = os.path.basename(out_folder)
        dest_mp4 = os.path.join(out_folder, f"{folder_stem}_ascii.mp4")

        self.is_busy = True
        self.active_task = "render"
        self.active_video_name = video["name"]
        self.active_target_folder = out_folder
        self.progress_pct = 0.0
        self.progress_current = 0
        self.progress_total = 0
        self.progress_fps = 0.0
        self.progress_eta = 0.0
        self.progress_bar_text = "[░░░░░░░░░░░░░░░░░░░░] 0.0%"
        self.progress_stage = "Render motoru başlatılıyor..."
        self.show_completion_modal = False

        cmd = [
            sys.executable,
            "-u",
            "ascii_video_renderer.py",
            "-i", video["path"],
            "-o", dest_mp4,
            "--quality", preset["id"],
            "--color-mode", color_mode_id,
            "--resolution", self.render_resolutions[self.selected_resolution_idx]["id"],
            "--overwrite",
            "--gui-progress",
        ]
        if self.crt_enabled:
            cmd.append("--crt")
        else:
            cmd.append("--no-crt")
        if self.audio_enabled:
            cmd.append("--audio")
        else:
            cmd.append("--no-audio")

        self.worker_thread = threading.Thread(
            target=self._run_subprocess_worker,
            args=(cmd, out_folder, "render"),
            daemon=True,
        )
        self.worker_thread.start()

    def launch_exporter(self) -> None:
        """Launch standalone single-file EXE exporter with real-time progress bar."""
        if self.is_busy:
            return
        if not self.videos or self.selected_video_idx < 0:
            self.status_message = "[UYARI] Önce bir video dosyası seçmelisiniz!"
            self.status_color = self.COLOR_RED
            return

        video = self.videos[self.selected_video_idx]
        preset = QUALITY_PRESETS[self.selected_quality_idx]
        color_mode_id = self.color_themes[self.selected_color_theme_idx]["id"]
        out_folder = get_video_output_dir(video["path"], "output")

        self.is_busy = True
        self.active_task = "export"
        self.active_video_name = video["name"]
        self.active_target_folder = out_folder
        self.progress_pct = 0.0
        self.progress_current = 0
        self.progress_total = 0
        self.progress_fps = 0.0
        self.progress_eta = 0.0
        self.progress_bar_text = "[░░░░░░░░░░░░░░░░░░░░] 0.0%"
        self.progress_stage = "ASCII Proje derleyicisi hazırlanıyor..."
        self.show_completion_modal = False

        cmd = [
            sys.executable,
            "-u",
            "ascii_exporter.py",
            "-i", video["path"],
            "-o", out_folder,
            "--quality", preset["id"],
            "--color-mode", color_mode_id,
            "--overwrite",
            "--build-exe",
            "--gui-progress",
        ]
        if self.crt_enabled:
            cmd.append("--crt")
        else:
            cmd.append("--no-crt")
        if self.audio_enabled:
            cmd.append("--audio")
        else:
            cmd.append("--no-audio")
        if self.loop_enabled:
            cmd.append("--loop")
        else:
            cmd.append("--no-loop")
        cmd.extend(["--seek-step", str(self.seek_step)])

        self.worker_thread = threading.Thread(
            target=self._run_subprocess_worker,
            args=(cmd, out_folder, "export"),
            daemon=True,
        )
        self.worker_thread.start()

    def draw(self) -> None:
        """Draw full GUI interface with exact bounding boxes."""
        sw, sh = self.width, self.height
        self.screen.fill(self.COLOR_BG)

        self.rendered_video_rects.clear()
        self.rendered_quality_rects.clear()
        self.rendered_buttons.clear()

        # 1. Top Header Bar
        header_rect = pygame.Rect(0, 0, sw, 46)
        pygame.draw.rect(self.screen, self.COLOR_PANEL_BG, header_rect)
        pygame.draw.line(self.screen, self.COLOR_BORDER, (0, 45), (sw, 45), 1)

        if self.icon_surf:
            scaled_icon = pygame.transform.smoothscale(self.icon_surf, (28, 28))
            self.screen.blit(scaled_icon, (16, 9))
            title_x = 52
        else:
            title_x = 18

        title_surf = self.font_title.render("RETRO ASCII VIDEO STUDIO", True, self.COLOR_AMBER)
        self.screen.blit(title_surf, (title_x, 12))

        sub_surf = self.font_small.render("v2.2 • ASCII oynatıcı ve dönüştürücü", True, self.COLOR_STEEL)
        self.screen.blit(sub_surf, (title_x + title_surf.get_width() + 14, 16))

        # 2. Left Panel: Video Explorer
        panel_top = 48
        panel_bottom = sh - 54
        panel_h = max(200, panel_bottom - panel_top)
        panel_w = (sw - 50) // 2
        left_panel_rect = pygame.Rect(20, panel_top, panel_w, panel_h)
        pygame.draw.rect(self.screen, self.COLOR_PANEL_BG, left_panel_rect, border_radius=6)
        pygame.draw.rect(self.screen, self.COLOR_BORDER, left_panel_rect, width=1, border_radius=6)

        # Video panel header
        v_head = self.font_header.render(f"VIDEOLAR ({len(self.videos)})", True, self.COLOR_WHITE)
        self.screen.blit(v_head, (32, panel_top + 6))

        # Refresh button
        ref_rect = pygame.Rect(panel_w - 75, panel_top + 3, 80, 20)
        pygame.draw.rect(self.screen, (28, 36, 52), ref_rect, border_radius=4)
        pygame.draw.rect(self.screen, self.COLOR_BORDER, ref_rect, width=1, border_radius=4)
        ref_txt = self.font_small.render("🔄 Yenile", True, self.COLOR_CYAN)
        self.screen.blit(ref_txt, (ref_rect.centerx - ref_txt.get_width() // 2, ref_rect.centery - ref_txt.get_height() // 2))
        self.rendered_buttons["REFRESH"] = ref_rect

        # Scrollable Video Items List
        list_rect = self.get_video_list_rect()
        total_videos_h = len(self.videos) * 37
        max_v_scroll = max(0, total_videos_h - list_rect.height)
        self.video_scroll_y = max(0, min(max_v_scroll, self.video_scroll_y))
        self.screen.set_clip(list_rect)

        y_cursor = panel_top + 28 - self.video_scroll_y
        item_h = 34
        if not self.videos:
            empty_surf = self.font_main.render("Klasörde video dosyası bulunamadı (.mp4...)", True, self.COLOR_MUTED)
            self.screen.blit(empty_surf, (36, panel_top + 40))
        else:
            for i, vid in enumerate(self.videos):
                item_rect = pygame.Rect(28, y_cursor, panel_w - 20, item_h)
                is_selected = (i == self.selected_video_idx)
                is_hovered = (i == self.hovered_video_idx)

                # Only register collision if within visible vertical viewport
                if item_rect.bottom > list_rect.top and item_rect.top < list_rect.bottom:
                    self.rendered_video_rects.append((i, item_rect))

                if is_selected:
                    pygame.draw.rect(self.screen, self.COLOR_PANEL_ACTIVE, item_rect, border_radius=4)
                    pygame.draw.rect(self.screen, self.COLOR_BORDER_FOCUS, item_rect, width=2, border_radius=4)
                elif is_hovered:
                    pygame.draw.rect(self.screen, self.COLOR_PANEL_HOVER, item_rect, border_radius=4)
                    pygame.draw.rect(self.screen, self.COLOR_BORDER_HOVER, item_rect, width=1, border_radius=4)
                else:
                    pygame.draw.rect(self.screen, (22, 26, 38), item_rect, border_radius=4)
                    pygame.draw.rect(self.screen, self.COLOR_BORDER, item_rect, width=1, border_radius=4)

                # Icon indicator
                icon_tag = "▶" if is_selected else ("·" if is_hovered else " ")
                tag_surf = self.font_main.render(icon_tag, True, self.COLOR_GREEN if is_selected else self.COLOR_CYAN)
                self.screen.blit(tag_surf, (36, y_cursor + (item_h - tag_surf.get_height()) // 2))

                # Video name
                name_col = self.COLOR_WHITE if is_selected else (self.COLOR_CYAN if is_hovered else self.COLOR_STEEL)
                name_surf = self.font_main.render(vid["name"], True, name_col)
                self.screen.blit(name_surf, (56, y_cursor + (item_h - name_surf.get_height()) // 2))

                # Video size
                size_surf = self.font_small.render(vid["size_str"], True, self.COLOR_MUTED)
                self.screen.blit(size_surf, (item_rect.right - size_surf.get_width() - 10, y_cursor + (item_h - size_surf.get_height()) // 2))

                y_cursor += item_h + 3

        self.screen.set_clip(None)

        # 3. Right Panel: Quality Presets
        right_x = panel_w + 30
        right_w = sw - right_x - 20
        right_panel_rect = pygame.Rect(right_x, panel_top, right_w, panel_h)
        pygame.draw.rect(self.screen, self.COLOR_PANEL_BG, right_panel_rect, border_radius=6)
        pygame.draw.rect(self.screen, self.COLOR_BORDER, right_panel_rect, width=1, border_radius=6)

        # Quality header
        q_head = self.font_header.render("KALİTE SEVİYESİ / PRESETS", True, self.COLOR_WHITE)
        self.screen.blit(q_head, (right_x + 16, panel_top + 6))
        self.rendered_buttons["HEADER_QUALITY"] = pygame.Rect(right_x + 12, panel_top + 4, right_w - 24, 20)

        # Scrollable Quality Cards
        settings_h = self.get_settings_height()
        q_list_rect = self.get_quality_list_rect()
        q_item_h = 28
        q_gap = 1
        total_presets_h = len(QUALITY_PRESETS) * (q_item_h + q_gap)
        viewport_presets_h = q_list_rect.height
        max_scroll = max(0, total_presets_h - viewport_presets_h)
        self.quality_scroll_y = max(0, min(max_scroll, self.quality_scroll_y))
        self.screen.set_clip(q_list_rect)

        q_cursor = q_list_rect.top - self.quality_scroll_y
        for i, preset in enumerate(QUALITY_PRESETS):
            card_rect = pygame.Rect(right_x + 12, q_cursor, right_w - 28, q_item_h)
            is_active = (i == self.selected_quality_idx)
            is_q_hover = (i == self.hovered_quality_idx)

            if card_rect.bottom > q_list_rect.top and card_rect.top < q_list_rect.bottom:
                self.rendered_quality_rects.append((i, card_rect))

            if is_active:
                pygame.draw.rect(self.screen, self.COLOR_PANEL_ACTIVE, card_rect, border_radius=4)
                pygame.draw.rect(self.screen, self.COLOR_BORDER_FOCUS, card_rect, width=2, border_radius=4)
            elif is_q_hover:
                pygame.draw.rect(self.screen, self.COLOR_PANEL_HOVER, card_rect, border_radius=4)
                pygame.draw.rect(self.screen, self.COLOR_BORDER_HOVER, card_rect, width=1, border_radius=4)
            else:
                pygame.draw.rect(self.screen, (22, 26, 38), card_rect, border_radius=4)
                pygame.draw.rect(self.screen, self.COLOR_BORDER, card_rect, width=1, border_radius=4)

            # Name & Tag (compact single-line layout)
            p_name = self.font_main.render(preset["name"], True, self.COLOR_AMBER if is_active else self.COLOR_WHITE)
            self.screen.blit(p_name, (card_rect.x + 8, card_rect.centery - p_name.get_height() // 2))

            tag_surf = self.font_small.render(preset["tag"], True, self.COLOR_CYAN if is_active else self.COLOR_MUTED)
            self.screen.blit(tag_surf, (card_rect.right - tag_surf.get_width() - 8, card_rect.centery - tag_surf.get_height() // 2))

            q_cursor += q_item_h + q_gap

        self.screen.set_clip(None)

        # Draw scrollbar for presets if overflow
        total_presets_h = len(QUALITY_PRESETS) * (q_item_h + q_gap)
        viewport_presets_h = q_list_rect.height
        max_scroll = max(0, total_presets_h - viewport_presets_h)
        if total_presets_h > viewport_presets_h:
            sb_x = right_x + right_w - 12
            sb_y = q_list_rect.top
            sb_w = 4
            sb_h = viewport_presets_h
            pygame.draw.rect(self.screen, (25, 30, 42), (sb_x, sb_y, sb_w, sb_h), border_radius=2)
            thumb_h = max(24, int(sb_h * (viewport_presets_h / total_presets_h)))
            thumb_y = sb_y + int((sb_h - thumb_h) * (self.quality_scroll_y / max_scroll))
            pygame.draw.rect(self.screen, self.COLOR_CYAN, (sb_x, thumb_y, sb_w, thumb_h), border_radius=2)

        # Settings Section Divider & Header
        sett_y = right_panel_rect.bottom - settings_h
        pygame.draw.line(self.screen, self.COLOR_BORDER, (right_x + 12, sett_y), (right_x + right_w - 12, sett_y), 1)
        sett_title = self.font_small.render("AYARLAR (Sol/Sağ Tık veya [C, S, L, T, Z, B, V] Tuşlarıyla Değiştirin)", True, self.COLOR_AMBER)
        self.screen.blit(sett_title, (right_x + 14, sett_y + 3))

        row_y = sett_y + 17
        row_h = 21
        card_gap = 1
        row_w = right_w - 24

        # 1. CRT Scanlines Card
        crt_rect = pygame.Rect(right_x + 12, row_y, row_w, row_h)
        crt_bg = (26, 36, 48) if self.crt_enabled else (18, 20, 28)
        pygame.draw.rect(self.screen, crt_bg, crt_rect, border_radius=3)
        pygame.draw.rect(self.screen, self.COLOR_GREEN if self.crt_enabled else self.COLOR_BORDER, crt_rect, width=1, border_radius=3)

        crt_title = self.font_main.render("[C] CRT Tarama Çizgileri & Tüp Efekti", True, self.COLOR_WHITE if self.crt_enabled else self.COLOR_MUTED)
        self.screen.blit(crt_title, (crt_rect.x + 8, crt_rect.centery - crt_title.get_height() // 2))

        crt_status_txt = "AÇIK [ON]" if self.crt_enabled else "KAPALI [OFF]"
        crt_status_surf = self.font_small.render(crt_status_txt, True, self.COLOR_GREEN if self.crt_enabled else self.COLOR_RED)
        self.screen.blit(crt_status_surf, (crt_rect.right - crt_status_surf.get_width() - 8, crt_rect.centery - crt_status_surf.get_height() // 2))
        self.rendered_buttons["TOGGLE_CRT"] = crt_rect

        # 2. Audio Card
        row_y += row_h + card_gap
        audio_rect = pygame.Rect(right_x + 12, row_y, row_w, row_h)
        audio_bg = (26, 36, 48) if self.audio_enabled else (18, 20, 28)
        pygame.draw.rect(self.screen, audio_bg, audio_rect, border_radius=3)
        pygame.draw.rect(self.screen, self.COLOR_GREEN if self.audio_enabled else self.COLOR_BORDER, audio_rect, width=1, border_radius=3)

        audio_title = self.font_main.render("[S] Ses Senkronizasyonu", True, self.COLOR_WHITE if self.audio_enabled else self.COLOR_MUTED)
        self.screen.blit(audio_title, (audio_rect.x + 8, audio_rect.centery - audio_title.get_height() // 2))

        audio_status_txt = "AÇIK [ON]" if self.audio_enabled else "KAPALI [OFF]"
        audio_status_surf = self.font_small.render(audio_status_txt, True, self.COLOR_GREEN if self.audio_enabled else self.COLOR_RED)
        self.screen.blit(audio_status_surf, (audio_rect.right - audio_status_surf.get_width() - 8, audio_rect.centery - audio_status_surf.get_height() // 2))
        self.rendered_buttons["TOGGLE_AUDIO"] = audio_rect

        # 3. Loop Card
        row_y += row_h + card_gap
        loop_rect = pygame.Rect(right_x + 12, row_y, row_w, row_h)
        loop_bg = (26, 36, 48) if self.loop_enabled else (18, 20, 28)
        pygame.draw.rect(self.screen, loop_bg, loop_rect, border_radius=3)
        pygame.draw.rect(self.screen, self.COLOR_GREEN if self.loop_enabled else self.COLOR_BORDER, loop_rect, width=1, border_radius=3)

        loop_title = self.font_main.render("[L] Sonsuz Video Döngüsü", True, self.COLOR_WHITE if self.loop_enabled else self.COLOR_MUTED)
        self.screen.blit(loop_title, (loop_rect.x + 8, loop_rect.centery - loop_title.get_height() // 2))

        loop_status_txt = "AÇIK [ON]" if self.loop_enabled else "KAPALI [OFF]"
        loop_status_surf = self.font_small.render(loop_status_txt, True, self.COLOR_GREEN if self.loop_enabled else self.COLOR_RED)
        self.screen.blit(loop_status_surf, (loop_rect.right - loop_status_surf.get_width() - 8, loop_rect.centery - loop_status_surf.get_height() // 2))
        self.rendered_buttons["TOGGLE_LOOP"] = loop_rect

        # 4. Color Theme Card
        row_y += row_h + card_gap
        theme_rect = pygame.Rect(right_x + 12, row_y, row_w, row_h)
        cur_theme = self.color_themes[self.selected_color_theme_idx]
        theme_bg = (24, 32, 48)
        pygame.draw.rect(self.screen, theme_bg, theme_rect, border_radius=3)
        pygame.draw.rect(self.screen, cur_theme["color"], theme_rect, width=1, border_radius=3)

        theme_title = self.font_main.render(f"[T] Renk Teması: {cur_theme['name']}", True, self.COLOR_WHITE)
        self.screen.blit(theme_title, (theme_rect.x + 8, theme_rect.centery - theme_title.get_height() // 2))

        theme_status_surf = self.font_small.render(f"[{cur_theme['tag']}]", True, cur_theme["color"])
        self.screen.blit(theme_status_surf, (theme_rect.right - theme_status_surf.get_width() - 8, theme_rect.centery - theme_status_surf.get_height() // 2))
        self.rendered_buttons["TOGGLE_COLOR"] = theme_rect

        # 5. Seek Step Card
        row_y += row_h + card_gap
        seek_rect = pygame.Rect(right_x + 12, row_y, row_w, row_h)
        seek_bg = (26, 36, 48)
        pygame.draw.rect(self.screen, seek_bg, seek_rect, border_radius=3)
        pygame.draw.rect(self.screen, self.COLOR_CYAN, seek_rect, width=1, border_radius=3)

        seek_title = self.font_main.render(f"[Z] Hızlı Sarma Adımı: ±{int(self.seek_step)}s", True, self.COLOR_WHITE)
        self.screen.blit(seek_title, (seek_rect.x + 8, seek_rect.centery - seek_title.get_height() // 2))

        seek_status_surf = self.font_small.render(f"±{int(self.seek_step)} SANİYE", True, self.COLOR_CYAN)
        self.screen.blit(seek_status_surf, (seek_rect.right - seek_status_surf.get_width() - 8, seek_rect.centery - seek_status_surf.get_height() // 2))
        self.rendered_buttons["TOGGLE_SEEK"] = seek_rect

        # 6. Character Background Card
        row_y += row_h + card_gap
        bg_rect = pygame.Rect(right_x + 12, row_y, row_w, row_h)
        bg_card_color = (26, 36, 48) if self.clean_bg_enabled else (36, 30, 24)
        pygame.draw.rect(self.screen, bg_card_color, bg_rect, border_radius=3)
        pygame.draw.rect(self.screen, self.COLOR_GREEN if self.clean_bg_enabled else self.COLOR_AMBER, bg_rect, width=1, border_radius=3)

        bg_title = self.font_main.render("[B] Karakter Arka Planı", True, self.COLOR_WHITE)
        self.screen.blit(bg_title, (bg_rect.x + 8, bg_rect.centery - bg_title.get_height() // 2))

        bg_status_txt = "SİYAH" if self.clean_bg_enabled else "RENKLİ"
        bg_status_surf = self.font_small.render(bg_status_txt, True, self.COLOR_GREEN if self.clean_bg_enabled else self.COLOR_AMBER)
        self.screen.blit(bg_status_surf, (bg_rect.right - bg_status_surf.get_width() - 8, bg_rect.centery - bg_status_surf.get_height() // 2))
        self.rendered_buttons["TOGGLE_BG"] = bg_rect

        # 7. Render Resolution Card
        row_y += row_h + card_gap
        res_rect = pygame.Rect(right_x + 12, row_y, row_w, row_h)
        cur_res = self.render_resolutions[self.selected_resolution_idx]
        res_bg = (24, 32, 48)
        pygame.draw.rect(self.screen, res_bg, res_rect, border_radius=3)
        pygame.draw.rect(self.screen, self.COLOR_CYAN, res_rect, width=1, border_radius=3)

        res_title = self.font_main.render(f"[V] Render Çözünürlüğü: {cur_res['name']}", True, self.COLOR_WHITE)
        self.screen.blit(res_title, (res_rect.x + 8, res_rect.centery - res_title.get_height() // 2))

        res_status_surf = self.font_small.render(f"[{cur_res['tag']}]", True, self.COLOR_CYAN)
        self.screen.blit(res_status_surf, (res_rect.right - res_status_surf.get_width() - 8, res_rect.centery - res_status_surf.get_height() // 2))
        self.rendered_buttons["TOGGLE_RESOLUTION"] = res_rect

        # 4. Bottom Action Bar
        btn_y = sh - 50
        btn_h = 32
        gap = 10
        quit_w = 90
        avail_w = sw - 40 - quit_w - (3 * gap)

        play_w = max(150, int(avail_w * 0.28))
        render_w = max(170, int(avail_w * 0.36))
        build_w = avail_w - play_w - render_w

        # Button 1: Live Play
        m_pos = pygame.mouse.get_pos()
        play_rect = pygame.Rect(20, btn_y, play_w, btn_h)
        is_play_target = self.is_dragging_video and play_rect.collidepoint(m_pos)
        pygame.draw.rect(self.screen, (30, 70, 45) if is_play_target else (20, 50, 32), play_rect, border_radius=6)
        pygame.draw.rect(self.screen, self.COLOR_GREEN, play_rect, width=3 if is_play_target else 2, border_radius=6)
        play_txt = self.font_header.render("▶  OYNAT", True, self.COLOR_GREEN)
        self.screen.blit(play_txt, (play_rect.centerx - play_txt.get_width() // 2, play_rect.centery - play_txt.get_height() // 2))
        self.rendered_buttons["PLAY"] = play_rect

        # Button 2: Render MP4 Video
        render_x = play_rect.right + gap
        render_rect = pygame.Rect(render_x, btn_y, render_w, btn_h)
        is_render_target = self.is_dragging_video and render_rect.collidepoint(m_pos)
        pygame.draw.rect(self.screen, (70, 50, 25) if is_render_target else (50, 36, 18), render_rect, border_radius=6)
        pygame.draw.rect(self.screen, self.COLOR_AMBER, render_rect, width=3 if is_render_target else 2, border_radius=6)
        render_txt = self.font_header.render("🎬  RENDER AL (MP4)", True, self.COLOR_AMBER)
        self.screen.blit(render_txt, (render_rect.centerx - render_txt.get_width() // 2, render_rect.centery - render_txt.get_height() // 2))
        self.rendered_buttons["RENDER"] = render_rect

        # Button 3: Build Standalone EXE
        build_x = render_rect.right + gap
        build_rect = pygame.Rect(build_x, btn_y, build_w, btn_h)
        is_build_target = self.is_dragging_video and build_rect.collidepoint(m_pos)
        pygame.draw.rect(self.screen, (28, 60, 90) if is_build_target else (20, 42, 64), build_rect, border_radius=6)
        pygame.draw.rect(self.screen, self.COLOR_CYAN, build_rect, width=3 if is_build_target else 2, border_radius=6)
        build_txt = self.font_header.render("📦  EXE OLUŞTUR", True, self.COLOR_CYAN)
        self.screen.blit(build_txt, (build_rect.centerx - build_txt.get_width() // 2, build_rect.centery - build_txt.get_height() // 2))
        self.rendered_buttons["EXPORT"] = build_rect

        # Button 4: Quit
        quit_x = build_rect.right + gap
        quit_rect = pygame.Rect(quit_x, btn_y, quit_w, btn_h)
        pygame.draw.rect(self.screen, (36, 20, 24), quit_rect, border_radius=6)
        pygame.draw.rect(self.screen, self.COLOR_RED, quit_rect, width=1, border_radius=6)
        quit_txt = self.font_header.render("✕  ÇIKIŞ", True, self.COLOR_RED)
        self.screen.blit(quit_txt, (quit_rect.centerx - quit_txt.get_width() // 2, quit_rect.centery - quit_txt.get_height() // 2))
        self.rendered_buttons["QUIT"] = quit_rect

        # 5. Status Bar at Bottom
        if self.is_busy:
            status_text = f"DURUM: {self.progress_bar_text}"
            status_color = self.COLOR_CYAN if self.active_task == "export" else self.COLOR_AMBER
        elif self.is_dragging_video and 0 <= self.dragging_video_idx < len(self.videos):
            status_text = f"SÜRÜKLENİYOR: {self.videos[self.dragging_video_idx]['name']} (RENDER AL veya EXE üzerine bırakın)"
            status_color = self.COLOR_AMBER
        elif 0 <= self.hovered_quality_idx < len(QUALITY_PRESETS):
            hp = QUALITY_PRESETS[self.hovered_quality_idx]
            status_text = f"ÖN AYAR: {hp['name']} — {hp['desc']}"
            status_color = self.COLOR_CYAN
        else:
            status_text = f"DURUM: {self.status_message}"
            status_color = self.status_color

        status_surf = self.font_small.render(status_text, True, status_color)
        self.screen.blit(status_surf, (22, sh - 15))

        # 6. Center Progress / Completion Modal Overlay
        self.draw_modal()

        # 7. Floating drag badge following cursor
        if self.is_dragging_video and 0 <= self.dragging_video_idx < len(self.videos):
            vid = self.videos[self.dragging_video_idx]
            mx, my = pygame.mouse.get_pos()
            badge_w = 270
            badge_h = 42
            badge_rect = pygame.Rect(mx - 135, my - 21, badge_w, badge_h)
            badge_surf = pygame.Surface((badge_w, badge_h), pygame.SRCALPHA)
            badge_surf.fill((16, 24, 40, 235))
            pygame.draw.rect(badge_surf, self.COLOR_CYAN, (0, 0, badge_w, badge_h), width=2, border_radius=6)
            self.screen.blit(badge_surf, badge_rect)
            b_icon = self.font_header.render("🎞️ SÜRÜKLENİYOR:", True, self.COLOR_AMBER)
            self.screen.blit(b_icon, (badge_rect.x + 10, badge_rect.y + 4))
            v_name = vid["name"] if len(vid["name"]) <= 28 else vid["name"][:25] + "..."
            b_name = self.font_small.render(v_name, True, self.COLOR_WHITE)
            self.screen.blit(b_name, (badge_rect.x + 10, badge_rect.y + 22))

    def draw_modal(self) -> None:
        """Render high-visibility progress modal or completion popup on top."""
        if not self.is_busy and not self.show_completion_modal:
            return

        sw, sh = self.width, self.height
        self.modal_buttons.clear()

        # Dimmed backdrop overlay
        backdrop = pygame.Surface((sw, sh), pygame.SRCALPHA)
        backdrop.fill((8, 10, 16, 215))
        self.screen.blit(backdrop, (0, 0))

        mw = min(680, sw - 40)
        mh = 290
        mx = (sw - mw) // 2
        my = (sh - mh) // 2
        modal_rect = pygame.Rect(mx, my, mw, mh)

        # Border color based on task / state
        if self.show_completion_modal and not self.is_busy:
            accent_col = self.COLOR_GREEN if self.completion_success else self.COLOR_RED
        elif self.active_task == "render":
            accent_col = self.COLOR_AMBER
        else:
            accent_col = self.COLOR_CYAN

        # Modal panel
        pygame.draw.rect(self.screen, (16, 20, 30), modal_rect, border_radius=10)
        pygame.draw.rect(self.screen, accent_col, modal_rect, width=2, border_radius=10)

        # Header bar in modal
        header_h = 44
        m_head_rect = pygame.Rect(mx, my, mw, header_h)
        pygame.draw.rect(self.screen, (22, 28, 42), m_head_rect, border_top_left_radius=10, border_top_right_radius=10)
        pygame.draw.line(self.screen, self.COLOR_BORDER, (mx, my + header_h), (mx + mw, my + header_h), 1)

        if self.is_busy:
            title_text = "🎬  MP4 VİDEO RENDER ALINIYOR" if self.active_task == "render" else "📦  EXE PROJESİ DERLENİYOR"
            title_surf = self.font_header.render(title_text, True, accent_col)
            self.screen.blit(title_surf, (mx + 20, my + 13))

            # Video & Target Directory
            vid_surf = self.font_main.render(f"Video: {self.active_video_name}", True, self.COLOR_WHITE)
            self.screen.blit(vid_surf, (mx + 20, my + 54))

            target_surf = self.font_small.render(f"Hedef: {self.active_target_folder}", True, self.COLOR_CYAN)
            self.screen.blit(target_surf, (mx + 20, my + 76))

            # Large Percentage Text
            pct_val = max(0.0, min(100.0, self.progress_pct))
            pct_surf = self.font_big_pct.render(f"{pct_val:5.1f}%", True, accent_col)
            self.screen.blit(pct_surf, (mx + mw - pct_surf.get_width() - 25, my + 52))

            # Graphical Progress Bar
            bar_x = mx + 20
            bar_y = my + 104
            bar_w = mw - 40
            bar_h = 24
            bar_slot = pygame.Rect(bar_x, bar_y, bar_w, bar_h)
            pygame.draw.rect(self.screen, (10, 13, 20), bar_slot, border_radius=4)
            pygame.draw.rect(self.screen, self.COLOR_BORDER, bar_slot, width=1, border_radius=4)

            fill_w = int(bar_w * (pct_val / 100.0))
            if fill_w > 0:
                fill_rect = pygame.Rect(bar_x, bar_y, fill_w, bar_h)
                pygame.draw.rect(self.screen, accent_col, fill_rect, border_radius=4)
                pygame.draw.line(self.screen, (255, 255, 255), (bar_x + 1, bar_y + 1), (bar_x + fill_w - 1, bar_y + 1), 1)

            # Text Progress representation
            p_text = self.progress_bar_text if self.progress_bar_text else f"[{'█' * int(20 * pct_val / 100.0) + '░' * (20 - int(20 * pct_val / 100.0))}] {pct_val:5.1f}%"
            text_surf = self.font_header.render(p_text, True, self.COLOR_WHITE)
            self.screen.blit(text_surf, (mx + (mw - text_surf.get_width()) // 2, my + 138))

            # Active Stage
            stage_surf = self.font_main.render(f"Aşama: {self.progress_stage}", True, self.COLOR_STEEL)
            self.screen.blit(stage_surf, (mx + 20, my + 174))

            # Stats (frames / FPS / ETA) if available
            if self.progress_total > 0 and self.progress_current > 0:
                stats_str = f"İşlenen: {self.progress_current}/{self.progress_total} kare | Hız: {self.progress_fps:.1f} FPS | Kalan: ~{self.progress_eta:.1f}s"
                stats_surf = self.font_small.render(stats_str, True, self.COLOR_MUTED)
                self.screen.blit(stats_surf, (mx + 20, my + 204))

            # Pulsing / Animated terminal spinner notice
            spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            spin_idx = (pygame.time.get_ticks() // 100) % len(spinner_chars)
            notice_str = f"{spinner_chars[spin_idx]} İşlem sürüyor..."
            notice_surf = self.font_small.render(notice_str, True, accent_col)
            self.screen.blit(notice_surf, (mx + 20, my + 250))

        else:
            # Completion modal
            title_text = "✅  İŞLEM TAMAMLANDI" if self.completion_success else "❌  İŞLEM TAMAMLANAMADI"
            title_surf = self.font_header.render(title_text, True, accent_col)
            self.screen.blit(title_surf, (mx + 20, my + 13))

            desc_lines: list[str] = []
            for item in [self.completion_message, f"Klasör: {self.completion_folder}", "Windows Gezgini'nde klasör otomatik açıldı." if self.completion_success else ""]:
                if item:
                    for sub in str(item).split("\n"):
                        clean_sub = sub.strip()
                        if clean_sub and clean_sub not in desc_lines:
                            desc_lines.append(clean_sub)

            dy = my + 60
            for i, line in enumerate(desc_lines):
                col = self.COLOR_WHITE if i == 0 else self.COLOR_STEEL
                l_surf = self.font_main.render(line, True, col)
                self.screen.blit(l_surf, (mx + 20, dy))
                dy += 24

            # Action Buttons: Open Folder & Dismiss
            btn_h = 38
            btn_w = 200
            btn_y = my + mh - 54

            # Open folder button
            of_rect = pygame.Rect(mx + 30, btn_y, btn_w, btn_h)
            pygame.draw.rect(self.screen, (20, 42, 64), of_rect, border_radius=6)
            pygame.draw.rect(self.screen, self.COLOR_CYAN, of_rect, width=1, border_radius=6)
            of_txt = self.font_main.render("📁  KLASÖRÜ AÇ", True, self.COLOR_CYAN)
            self.screen.blit(of_txt, (of_rect.centerx - of_txt.get_width() // 2, of_rect.centery - of_txt.get_height() // 2))
            self.modal_buttons["OPEN_FOLDER"] = of_rect

            # Close button
            cl_rect = pygame.Rect(mx + mw - btn_w - 30, btn_y, btn_w, btn_h)
            pygame.draw.rect(self.screen, (20, 50, 32), cl_rect, border_radius=6)
            pygame.draw.rect(self.screen, self.COLOR_GREEN, cl_rect, width=1, border_radius=6)
            cl_txt = self.font_main.render("✓  KAPAT", True, self.COLOR_GREEN)
            self.screen.blit(cl_txt, (cl_rect.centerx - cl_txt.get_width() // 2, cl_rect.centery - cl_txt.get_height() // 2))
            self.modal_buttons["CLOSE_MODAL"] = cl_rect


def main() -> int:
    """Launch the ASCII Studio GUI."""
    from studio_main import main as launch
    return launch()


if __name__ == "__main__":
    sys.exit(main())

