import ctypes
import os
import sys

# Click-through overlay (extended window style)
WS_EX_TRANSPARENT = 0x20
WS_EX_LAYERED = 0x80000


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def make_click_through(hwnd):
    style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
    style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
    ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)


def get_global_mouse_pos():
    point = _POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def get_resource_path(relative_path):
    """Absolute path to a bundled or dev resource (PyInstaller or script dir)."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)
