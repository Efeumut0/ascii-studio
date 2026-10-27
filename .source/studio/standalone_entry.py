import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


def main():
    from standalone_template.run import main as play

    if getattr(sys, "frozen", False) and zipfile.is_zipfile(sys.executable):
        with tempfile.TemporaryDirectory(prefix="ascii-player-") as folder:
            root = Path(folder)
            with zipfile.ZipFile(sys.executable) as archive:
                allowed = {"config.json", "chars.npy", "colors.npy", "audio.wav"}
                if not {"config.json", "chars.npy", "colors.npy"}.issubset(archive.namelist()):
                    return 1
                for name in allowed.intersection(archive.namelist()):
                    with archive.open(name) as source, (root / name).open("wb") as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
            sys.argv[1:1] = ["--config", str(root / "config.json")]
            return play()
    return play()


if __name__ == "__main__":
    raise SystemExit(main())
