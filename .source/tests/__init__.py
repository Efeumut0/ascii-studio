"""
E2E Test Suite Package for Video-to-ASCII System.

This package provides:
- Common constants and paths (test.mp4, asci.mp4, root directory)
- Headless Pygame environment setup
- Contract helpers and defensive module importers
"""

import os
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Configure headless SDL audio/video drivers if not already set
if "SDL_VIDEODRIVER" not in os.environ:
    os.environ["SDL_VIDEODRIVER"] = "dummy"
if "SDL_AUDIODRIVER" not in os.environ:
    os.environ["SDL_AUDIODRIVER"] = "dummy"

TEST_MP4_PATH = os.path.join(PROJECT_ROOT, "test.mp4")
ASCI_MP4_PATH = os.path.join(PROJECT_ROOT, "asci.mp4")
DEFAULT_RAMP = " .:-=+*#%@"

# Defensive module imports
try:
    import ascii_engine.video_decoder as video_decoder_mod
except ImportError:
    video_decoder_mod = None

try:
    import ascii_engine.audio_engine as audio_engine_mod
except ImportError:
    audio_engine_mod = None

try:
    import ascii_ui.renderer as renderer_mod
except ImportError:
    renderer_mod = None

try:
    import ascii_ui.crt_effects as crt_effects_mod
except ImportError:
    crt_effects_mod = None

try:
    import ascii_ui.hud as hud_mod
except ImportError:
    hud_mod = None

try:
    import ascii_ui.input_handler as input_handler_mod
except ImportError:
    input_handler_mod = None

try:
    import ascii_player as ascii_player_mod
except ImportError:
    ascii_player_mod = None

try:
    import ascii_exporter as ascii_exporter_mod
except ImportError:
    ascii_exporter_mod = None
