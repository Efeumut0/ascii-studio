"""Retro ASCII Video Studio - PythonW Silent Launcher.

Launches the GUI without showing a terminal / console window in the background on Windows.
"""
import sys

from ascii_gui import main

if __name__ == "__main__":
    sys.exit(main())
