import os
import sys

from PyQt6.QtCore import QLockFile
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

from config import configure_logging, ensure_config_dir, get_config_dir, logger
from overlay import TaskbarCatOverlay


def main():
    configure_logging()

    # One tray app per session — without this, each launch spawns another process
    # (double-click, shortcut, autostart + manual, etc.).
    _instance_lock = None
    if "-testing" not in sys.argv and "--testing" not in sys.argv:
        ensure_config_dir()
        lock_path = os.path.join(get_config_dir(), "taskbar_cat.lock")
        _instance_lock = QLockFile(lock_path)
        if not _instance_lock.tryLock():
            logger.info("Taskbar Cat is already running; exiting.")
            sys.exit(0)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        logger.warning("System tray is not available. You may need to use Task Manager to quit.")

    TaskbarCatOverlay(app)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
