"""Graphite keyboard guide shared by the live and exported players."""

from functools import lru_cache

import pygame

BACKGROUND = (36, 38, 40)
BORDER = (69, 70, 70)
TEXT = (238, 234, 229)
MUTED = (178, 173, 166)
ACCENT = (212, 170, 126)


def shortcut_rows(language="tr", seek_step=5, standalone=False):
    english = language == "en"
    step = f"{float(seek_step):g}"
    if not english:
        step = step.replace(".", ",")
    rows = [
        ("Space", "Play / pause" if english else "Oynat / duraklat"),
        ("↑ / ↓", "Speed: 0.5× – 2×" if english else "Hız: 0,5× – 2×"),
        ("← / →", f"Seek back / ahead: {step} s" if english else f"Geri / ileri: {step} sn"),
        ("Z", "Change seek interval" if english else "Sarma adımını değiştir"),
        ("M / S / A", "Mute / unmute" if english else "Sesi aç / kapat"),
        ("L", "Loop on / off" if english else "Döngüyü aç / kapat"),
        ("C / R", "CRT effect on / off" if english else "CRT efektini aç / kapat"),
        ("T", "Change color palette" if english else "Renk paletini değiştir"),
    ]
    if standalone:
        rows.append(("F / F11", "Fullscreen / window" if english else "Tam ekran / pencere"))
    else:
        rows.append(("Tab", "Show / hide info" if english else "Bilgileri göster / gizle"))
    rows.extend([
        ("F1 / H", "Show / hide help" if english else "Yardımı aç / kapat"),
        ("Esc / Q", "Exit when help is closed" if english else "Yardım kapalıyken çık"),
    ])
    return rows


@lru_cache(maxsize=32)
def _panel(language, seek_step, standalone, compact):
    if not pygame.font.get_init():
        pygame.font.init()
    rows = shortcut_rows(language, seek_step, standalone)
    columns = 1 if compact else 2
    count = (len(rows) + columns - 1) // columns
    row_height = 29 if compact else 44
    width = 440 if compact else 776
    height = 126 + count * row_height
    panel = pygame.Surface((width, height), pygame.SRCALPHA)
    pygame.draw.rect(panel, BACKGROUND, panel.get_rect(), border_radius=14)
    pygame.draw.rect(panel, BORDER, panel.get_rect(), width=1, border_radius=14)
    title_font = pygame.font.SysFont("bahnschrift", 25)
    body_font = pygame.font.SysFont("segoeui", 15)
    key_font = pygame.font.SysFont("consolas", 13)
    small_font = pygame.font.SysFont("segoeui", 12)

    def text(value, font, color, position):
        panel.blit(font.render(value, True, color), position)

    english = language == "en"
    text("Keyboard shortcuts" if english else "Klavye kısayolları", title_font, TEXT, (24, 20))
    text("ASCII / STUDIO", small_font, ACCENT, (width - 124, 27))
    pygame.draw.line(panel, BORDER, (24, 67), (width - 24, 67))
    column_width = (width - 48) // columns
    for index, (key, description) in enumerate(rows):
        column, row = divmod(index, count)
        x, y = 24 + column * column_width, 82 + row * row_height
        key_rect = pygame.Rect(x, y, 88, 23)
        pygame.draw.rect(panel, (45, 47, 49), key_rect, border_radius=5)
        pygame.draw.rect(panel, BORDER, key_rect, width=1, border_radius=5)
        label = key_font.render(key, True, ACCENT)
        panel.blit(label, label.get_rect(center=key_rect.center))
        text(description, body_font, TEXT, (x + 100, y + 2))
    pygame.draw.line(panel, BORDER, (24, height - 38), (width - 24, height - 38))
    text("F1 / H / Esc · Close help" if english else "F1 / H / Esc · Yardımı kapat",
         small_font, MUTED, (24, height - 27))
    return panel


def draw_help_overlay(screen, *, language="tr", seek_step=5, standalone=False):
    """Draw the guide and return its visible bounds inside the player window."""
    width, height = screen.get_size()
    dim = pygame.Surface((width, height), pygame.SRCALPHA)
    dim.fill((10, 11, 12, 190))
    screen.blit(dim, (0, 0))
    panel = _panel(language, float(seek_step), standalone, width < 680)
    scale = min(1, max(1, width - 24) / panel.get_width(), max(1, height - 24) / panel.get_height())
    if scale < 1:
        panel = pygame.transform.smoothscale(panel, (max(1, round(panel.get_width() * scale)),
                                                    max(1, round(panel.get_height() * scale))))
    bounds = panel.get_rect(center=screen.get_rect().center)
    screen.blit(panel, bounds)
    return bounds
