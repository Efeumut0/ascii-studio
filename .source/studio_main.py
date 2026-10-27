import sys


def main():
    if "--worker" in sys.argv:
        from studio.worker import run_worker
        return run_worker(sys.argv[sys.argv.index("--worker") + 1])
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ascii.studio.graphite")
    from PySide6.QtWidgets import QApplication

    from studio.window import StudioWindow

    app = QApplication(sys.argv)
    app.setApplicationName("ASCII Studio")
    app.setOrganizationName("ASCII Studio")
    window = StudioWindow()
    window.show()
    if "--screenshot" in sys.argv:
        from PySide6.QtCore import QTimer
        path = sys.argv[sys.argv.index("--screenshot") + 1]
        QTimer.singleShot(1200, lambda: window.grab().save(path))
    if "--smoke-test" in sys.argv:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
