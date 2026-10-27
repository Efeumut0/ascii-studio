# Project: Video-to-ASCII System

The application plays videos as colored ASCII, renders ASCII MP4 files, and exports standalone players.

The release starts with `ASCII Studio.exe` in the parent folder. Inputs are kept in `videos/` and outputs in `output/<video_name>/`. This hidden `.source/` directory contains developer files.

## Architecture

- `studio_main.py`: frozen application and worker entry point.
- `studio/window.py`: Graphite PySide6 interface and live Turkish/English switching.
- `studio/model.py`: settings validation, persistence, and application paths.
- `studio/worker.py`: background playback, rendering, and export dispatch.
- `studio/portable.py`: streaming frame conversion and standalone EXE packaging.
- `ascii_gui.py`: compatibility launcher and previous GUI components used by legacy tests.
- `ascii_player.py`: live playback with audio, seeking, and keyboard controls.
- `ascii_video_renderer.py`: MP4 rendering through PyAV.
- `ascii_exporter.py`: standalone project export and optional EXE build.
- `ascii_engine/`: video decoding, ASCII conversion, audio extraction, and playback timing.
- `ascii_ui/`: glyph rendering, CRT effects, playback controls, and HUD.
- `standalone_template/`: player and launchers copied into exported projects.
- `tests/`: unit tests, integration tests, and benchmarks.

## Running the application

Double-click `ASCII Studio.exe` in the parent folder. Use the TR/EN selector to switch language. Advanced settings expose custom columns, character ramps, font size, frame rate, aspect ratio, seek interval, HUD, encoder speed, workers, compression, and output location.

The Python modules also accept command-line arguments. Run a module with `--help` to list its options.

## Output

Renders and video EXEs are saved under `output/<video_name>/` beside the application. The shipped application and generated video EXEs require no Python or PyInstaller installation. PyInstaller is only needed to rebuild the application from source.

## Interface contracts

`VideoDecoder` provides metadata and yields timestamps, character indices, and RGB arrays. `iter_frames_at_fps()` samples frames at a specified rate. `seek()` changes playback position; `close()` releases the container.

`AudioEngine` extracts stereo PCM audio and manages playback, pause, resume, seek, and the playback clock.

`AsciiRenderer` draws character and color arrays. `CrtEffect` applies scanlines, vignette, and optional bloom. `HudRenderer` draws playback information and help; `InputHandler` handles keyboard and window events.

## Tests

See `TEST_INFRA.md` for commands and test groups. `TEST_READY.md` records the latest verification result.
