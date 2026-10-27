<div align="center">

# ASCII Studio

Play videos as ASCII art. Export them as MP4 files or standalone Windows players.

Windows &nbsp; / &nbsp; Python + PySide6 &nbsp; / &nbsp; Türkçe · English

[Workspace](#the-workspace) · [Outputs](#choose-an-output) · [Controls](#player-controls) · [Build from source](#build-from-source)

</div>

<br>

<img src="https://github.com/user-attachments/assets/1ab1caf4-94e4-489d-8864-5ac402fe060e" alt="ASCII Studio's Graphite workspace with video selection, character density, color palette and export controls" width="100%">

<p align="center"><sub>The Graphite workspace. Preview settings and export controls stay on one screen.</sub></p>

## The workspace

ASCII Studio turns video frames into colored characters and plays them with synchronized audio. The desktop interface handles file selection, appearance settings and export jobs. The player opens separately, with keyboard controls and an F1 guide.

Add a video, drop files into the window, or choose a folder. Select a file, set its appearance, then preview it or create an output.

The interface switches between Turkish and English. Advanced settings keep less common controls out of the main workspace.

## Choose an output

| Action | Result | Use it for |
| :--- | :--- | :--- |
| **Play** | An interactive ASCII player with audio and keyboard controls | Checking the look and adjusting playback |
| **Create MP4** | A rendered video with the chosen ASCII appearance | Uploading, editing or watching in a video player |
| **Create EXE** | A standalone Windows player containing the converted frames and optional audio | Sharing playback without a separate Python installation |

The exported EXE keeps the player controls. The MP4 contains the rendered result.

## Shape the image

| Setting | What it changes |
| :--- | :--- |
| Character density | Choose from 15 presets, or set a custom width of 20–450 columns. |
| Color palette | Original RGB, grayscale, green terminal, amber, or cyan/pink. |
| Resolution | Original size, 720p, 1080p, 2K, 4K, or custom dimensions. |
| Frame rate | Use the source rate or choose an output rate up to 60 FPS. |
| Audio | Include or omit audio in playback and generated files. |
| CRT effect | Add scanlines and a vignette. |

Advanced settings include a custom character ramp, font size, character proportions, seek interval, player information bars, encoder speed, compression and output folder.

More columns preserve finer detail, but increase the work needed to convert and draw each frame. For MP4 export, a lower CRF value gives higher quality and a larger file.

## Player controls

Press **F1** in the player to open the keyboard guide. Closing the guide leaves the current play/pause state unchanged.

| Key | Action |
| :--- | :--- |
| `Space` | Play / pause |
| `↑` / `↓` | Adjust speed from 0.5× to 2× |
| `←` / `→` | Seek backward / forward |
| `Z` | Cycle the seek interval: 5, 10, 30 or 60 seconds |
| `M` / `S` / `A` | Mute / unmute |
| `L` | Toggle looping |
| `C` / `R` | Toggle CRT effects |
| `T` | Cycle color palettes |
| `F1` / `H` | Show / hide the keyboard guide |
| `Esc` / `Q` | Close the guide first; exit playback when it is closed¹ |

The live player also uses `Tab` to show or hide its information bars. In the exported player, `F` or `F11` switches between windowed and fullscreen playback.

¹ In the exported player, `Esc` / `Q` also hides visible information bars before exiting.

Audio pauses at playback speeds other than 1× and resumes when normal speed is restored.

<details>
<summary>View the F1 keyboard guide</summary>

<br>

<img src="https://github.com/user-attachments/assets/bc138023-b4d4-4bfc-9e18-a7c1fd637e2a" alt="Graphite keyboard guide showing playback and appearance shortcuts in the exported player" width="100%">

The guide follows the selected interface language and displays the current seek interval. Its layout adapts to smaller player windows.

</details>

## Formats and internals

The file picker accepts **MP4, MKV, AVI, MOV, WebM, FLV, WMV and M4V**. Whether a particular file decodes depends on its codec and contents.

| Component | Role |
| :--- | :--- |
| Python + PySide6 | Desktop interface and settings |
| Pygame | Interactive playback, audio and keyboard input |
| NumPy | Character and color frame data |
| PyAV + OpenCV | Video decoding and conversion |
| PyInstaller | Windows application and standalone player packaging |

The packaged desktop app and exported players run without Python installed. The exported player reads frame arrays from disk instead of loading the entire video into memory.

<details>
<summary>Verification record</summary>

The local Windows source verification run on **28 October 2026** passed **361 tests** using generated video patterns and stereo tones. It covered playback and export behavior, settings, hover feedback, window corners and the F1 guide.

Separate checks on 27 October ran the packaged application without Python on PATH, rendered MP4 output, and opened generated players with and without audio. These are local results; this repository does not currently have a published CI workflow.

</details>

## Build from source

The Python modules live in [`.source/`](.source/). On Windows, with Python 3.11 installed, run these commands from the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .source\requirements.txt
.\.venv\Scripts\python.exe .source\studio_main.py
```

To build the desktop EXE and the player needed for standalone video exports:

```powershell
.\.venv\Scripts\python.exe .source\tools\build_studio.py
```

The result is `ASCII Studio.exe` at the repository root. [Development notes](.source/DEVELOPMENT.md) cover the source layout, worker processes, build outputs and tests. Test videos are generated locally from patterns and tones; personal videos are not required.

## Downloads

Source code is available in this repository under .source/. Packaged Windows downloads (ASCII Studio.exe) are available on the [Releases](https://github.com/Efeumut0/ascii-studio/releases) page.

Found a problem or have a suggestion? [Open an issue](https://github.com/Efeumut0/ascii-studio/issues).
