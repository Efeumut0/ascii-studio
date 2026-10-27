import subprocess
import sys
from pathlib import Path


def build():
    source = Path(__file__).resolve().parents[1]
    release = source.parent if source.name == ".source" else source
    scratch = source / ".build"
    common = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed",
              "--paths", str(source), "--icon", str(source / "assets" / "eye_icon.ico"),
              "--specpath", str(scratch / "specs")]
    player_command = common + ["--name", "portable-player", "--distpath", str(source / "assets"),
                            "--workpath", str(scratch / "player"),
                            "--exclude-module", "PySide6", "--exclude-module", "av",
                            "--exclude-module", "cv2", "--exclude-module", "tkinter",
                            "--exclude-module", "matplotlib", "--exclude-module", "scipy",
                            "--add-data", str(source / "assets" / "eye_icon.png") + ";.",
                            "--add-data", str(source / "assets" / "eye_icon.ico") + ";.",
                            str(source / "studio" / "standalone_entry.py")]
    if "--studio-only" not in sys.argv:
        subprocess.run(player_command, cwd=source, check=True)
    subprocess.run(common + ["--name", "ASCII Studio", "--distpath", str(release),
                            "--workpath", str(scratch / "studio"),
                            "--exclude-module", "tkinter", "--exclude-module", "matplotlib",
                            "--exclude-module", "scipy", "--exclude-module", "IPython",
                            "--add-data", str(source / "assets" / "eye_icon.ico") + ";assets",
                            "--add-data", str(source / "assets" / "portable-player.exe") + ";assets",
                            str(source / "studio_main.py")], cwd=source, check=True)
    print(release / "ASCII Studio.exe")


if __name__ == "__main__":
    build()
