# Development

The commands below use PowerShell on Windows and start from the repository root. Python 3.11 is the tested interpreter.

## Install and run

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .source\requirements.txt
.\.venv\Scripts\python.exe .source\studio_main.py
```

The application creates `videos/`, `output/` and `.state/` beside `.source/`. The state directory stores settings and job logs. These directories are ignored by Git.

Playback and MP4 rendering work from source. Creating a video EXE also needs `assets/portable-player.exe`; build it with the command below before using that action.

## Build the Windows application

```powershell
.\.venv\Scripts\python.exe .source\tools\build_studio.py
```

The build first creates `.source/assets/portable-player.exe`, then bundles it into `ASCII Studio.exe` at the repository root. Both executables run without a separate Python installation. Build intermediates stay in `.source/.build/`.

After a full build, `--studio-only` rebuilds the desktop application while reusing the player binary. Run a full build again after changing `standalone_template/` or `studio/standalone_entry.py`.

`standalone_template/standalone_player.spec` is a checked-in build template used by the older exported-project workflow. Other generated `.spec` files are ignored.

## Run tests

Create the synthetic video fixtures, then run discovery from `.source/`:

```powershell
.\.venv\Scripts\python.exe .source\tools\make_test_media.py
Set-Location .source
..\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

The generator creates color patterns with stereo tones in `test.mp4` and `asci.mp4`. It preserves existing files. Generated videos are local test inputs and are not committed.

The tests cover video decoding, audio, settings, window behavior, worker processes and exports. Some performance assertions depend on the machine. See [TEST_INFRA.md](TEST_INFRA.md) for test groups and [TEST_READY.md](TEST_READY.md) for the recorded verification run.

## Source layout

| Path | Responsibility |
| :--- | :--- |
| `studio_main.py` | Desktop startup and worker entry point |
| `studio/window.py` | Graphite interface and job controls |
| `studio/model.py` | Settings validation, persistence and application paths |
| `studio/translations.py` | Turkish and English interface text |
| `studio/worker.py` | Playback, rendering and export jobs |
| `studio/portable.py` | Frame conversion and standalone player packaging |
| `ascii_engine/` | Video decoding and audio playback |
| `ascii_ui/` | Glyph rendering, effects, keyboard input and playback information |
| `standalone_template/` | Exported player and shared F1 guide |
| `tests/` | Unit and integration tests |

Workers report progress through JSON files. Exported players store frame arrays in an appended ZIP archive and read extracted arrays from disk using memory mapping. `ascii_gui.py` retains the older interface components for compatibility; its launcher opens the PySide6 application.
