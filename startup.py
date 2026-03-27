import os
import sys
import winreg

from config import logger


def get_startup_command_string():
    """Command line stored in Run key for autostart."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw_path = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    python_exec = pythonw_path if os.path.exists(pythonw_path) else sys.executable
    root = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(root, "main.py")
    return f'"{python_exec}" "{script_path}"'


def get_startup_registry_key():
    return winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
    )


def is_startup_enabled():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        )
        try:
            winreg.QueryValueEx(key, "TaskbarCat")
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    except Exception:
        return False


def add_to_startup(exe_path):
    try:
        key = get_startup_registry_key()
        winreg.SetValueEx(key, "TaskbarCat", 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
        return True
    except Exception as e:
        logger.exception("Error adding to startup: %s", e)
        return False


def remove_from_startup():
    try:
        key = get_startup_registry_key()
        winreg.DeleteValue(key, "TaskbarCat")
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return True
    except Exception as e:
        logger.exception("Error removing from startup: %s", e)
        return False
