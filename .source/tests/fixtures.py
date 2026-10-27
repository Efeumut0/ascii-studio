import contextlib
import io
import tempfile
from pathlib import Path

from ascii_exporter import export_video

_standalone_fixture = None


def standalone_project_dir():
    global _standalone_fixture
    if _standalone_fixture is None:
        temporary = tempfile.TemporaryDirectory(prefix="ascii-test-project-")
        project = Path(temporary.name) / "project"
        source = Path(__file__).resolve().parents[1] / "test.mp4"
        with contextlib.redirect_stdout(io.StringIO()):
            export_video(str(source), str(project), cols=80, audio=True, lang="en")
        _standalone_fixture = (temporary, project)
    return str(_standalone_fixture[1])
