import sys
import ctypes
import os
import winreg
import logging
import json

import yaml

from PyQt6 import QtCore
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QSystemTrayIcon,
    QMenu,
    QMessageBox,
    QVBoxLayout,
    QHBoxLayout,
    QSpinBox,
    QPushButton,
    QComboBox,
    QWidget,
    QWidgetAction,
    QFrame,
    QAbstractSpinBox,
    QCheckBox,
    QSizePolicy,
)
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt

# Tray / embedded menu theme: #9170ED #80A9F5 #C3D4DB white black
TRAY_MENU_QSS = """
QMenu {
    background-color: #ffffff;
    color: #000000;
    border: 1px solid #9170ED;
    border-radius: 16px;
    padding: 6px;
}
QFrame#trayPanel {
    background-color: #ffffff;
    color: #000000;
    border: none;
    border-radius: 16px;
}
QLabel {
    color: #000000;
    background: transparent;
}
QSpinBox {
    background-color: #ffffff;
    color: #000000;
    border: 1px solid #C3D4DB;
    border-radius: 16px;
    padding: 6px 12px;
    min-height: 24px;
    selection-background-color: #9170ED;
    selection-color: #ffffff;
}
QComboBox {
    background-color: #ffffff;
    color: #000000;
    border: 1px solid #C3D4DB;
    border-radius: 16px;
    padding: 6px 12px;
    padding-right: 28px;
    min-height: 24px;
    selection-background-color: #9170ED;
    selection-color: #ffffff;
}
QSpinBox:focus, QComboBox:focus {
    border: 1px solid #9170ED;
}
QCheckBox {
    color: #000000;
    spacing: 10px;
    font-weight: 500;
}
QCheckBox::indicator {
    width: 42px;
    height: 24px;
    border: 1px solid #C3D4DB;
    border-radius: 12px;
    background: #ffffff;
}
QCheckBox::indicator:checked {
    background: #9170ED;
    border: 1px solid #9170ED;
}
QPushButton#trayQuit {
    background-color: #ffffff;
    color: #000000;
    border: 1px solid #9170ED;
    border-radius: 16px;
    padding: 6px 14px;
    min-width: 72px;
}
QPushButton#trayQuit:hover {
    background-color: #80A9F5;
    color: #000000;
}
QPushButton#traySave {
    background-color: #9170ED;
    color: #ffffff;
    border: 1px solid #9170ED;
    border-radius: 16px;
    padding: 6px 14px;
    min-width: 72px;
    font-weight: 600;
}
QPushButton#traySave:hover {
    background-color: #80A9F5;
    border: 1px solid #80A9F5;
    color: #000000;
}
QPushButton#traySave:pressed {
    background-color: #6f52c4;
    border: 1px solid #6f52c4;
    color: #ffffff;
}
"""

# Make window click-through
WS_EX_TRANSPARENT = 0x20
WS_EX_LAYERED = 0x80000
WS_EX_TOPMOST = 0x00000008

# Window positioning constants
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
SWP_NOACTIVATE = 0x0010

logger = logging.getLogger("taskbar_cat")


def get_config_dir():
    """%APPDATA%\\TaskbarCat (Roaming)."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    return os.path.join(appdata, "TaskbarCat")


def ensure_config_dir():
    d = get_config_dir()
    os.makedirs(d, exist_ok=True)
    return d


def get_config_yaml_path():
    return os.path.join(get_config_dir(), "config.yaml")


def get_log_path():
    return os.path.join(get_config_dir(), "taskbar_cat.log")


def get_legacy_settings_json_path():
    """Previous portable JSON next to exe/script (migrated once)."""
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, "taskbar_cat_settings.json")


def configure_logging():
    """Configure logging to a local file and console fallback."""
    if logger.handlers:
        return

    logger.setLevel(logging.INFO)
    ensure_config_dir()
    log_path = get_log_path()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    try:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # If file logging is unavailable, keep console logging so errors are visible.
        pass

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

def make_click_through(hwnd):
    style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
    style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
    ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)

def set_window_topmost(hwnd):
    """Force window to stay on top, above taskbar - more aggressive approach"""
    # First, bring window to top
    ctypes.windll.user32.BringWindowToTop(hwnd)
    # Then set as topmost
    ctypes.windll.user32.SetWindowPos(
        hwnd,
        HWND_TOPMOST,
        0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_NOACTIVATE
    )
    # Force it again to ensure it sticks
    ctypes.windll.user32.SetWindowPos(
        hwnd,
        HWND_TOPMOST,
        0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
    )

def get_global_mouse_pos():
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    
    point = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y

def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Running as script, use script directory
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(base_path, relative_path)

def _merge_validated_settings(raw):
    """Merge dict into validated defaults."""
    default_settings = {
        "size": 150,
        "y_offset": 15,
        "x_offset": -10,
        "monitor_mode": "primary",
    }
    if not isinstance(raw, dict):
        return default_settings
    result = default_settings.copy()
    try:
        if "size" in raw and 50 <= int(raw["size"]) <= 500:
            result["size"] = int(raw["size"])
        if "y_offset" in raw and -200 <= int(raw["y_offset"]) <= 200:
            result["y_offset"] = int(raw["y_offset"])
        if "x_offset" in raw and -500 <= int(raw["x_offset"]) <= 500:
            result["x_offset"] = int(raw["x_offset"])
        if raw.get("monitor_mode") in ("primary", "all"):
            result["monitor_mode"] = raw["monitor_mode"]
    except (TypeError, ValueError):
        pass
    return result


def load_settings():
    """Load settings from %APPDATA%\\TaskbarCat\\config.yaml; migrate legacy JSON once."""
    default_settings = {
        "size": 150,
        "y_offset": 15,
        "x_offset": -10,
        "monitor_mode": "primary",
    }

    yaml_path = get_config_yaml_path()
    if os.path.exists(yaml_path):
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return _merge_validated_settings(data if data is not None else {})
        except Exception as e:
            logger.exception("Error loading YAML settings: %s", e)
            return default_settings

    legacy = get_legacy_settings_json_path()
    if os.path.exists(legacy):
        try:
            with open(legacy, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = _merge_validated_settings(data)
            save_settings(
                merged["size"],
                merged["y_offset"],
                merged["x_offset"],
                merged["monitor_mode"],
            )
            return merged
        except Exception as e:
            logger.exception("Error migrating legacy JSON settings: %s", e)
            return default_settings

    return default_settings


def save_settings(size, y_offset, x_offset, monitor_mode):
    """Save settings to AppData YAML (skips if -testing flag is set)."""
    if "-testing" in sys.argv or "--testing" in sys.argv:
        return

    ensure_config_dir()
    settings = {
        "size": int(size),
        "y_offset": int(y_offset),
        "x_offset": int(x_offset),
        "monitor_mode": monitor_mode,
    }

    try:
        with open(get_config_yaml_path(), "w", encoding="utf-8") as f:
            yaml.safe_dump(
                settings,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
    except Exception as e:
        logger.exception("Error saving settings: %s", e)

def get_startup_registry_key():
    """Get the registry key for startup programs"""
    return winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
    )

def is_startup_enabled():
    """Check if Taskbar Cat is set to start on boot"""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ
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
    """Add Taskbar Cat to Windows startup"""
    try:
        key = get_startup_registry_key()
        winreg.SetValueEx(key, "TaskbarCat", 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
        return True
    except Exception as e:
        logger.exception("Error adding to startup: %s", e)
        return False

def remove_from_startup():
    """Remove Taskbar Cat from Windows startup"""
    try:
        key = get_startup_registry_key()
        winreg.DeleteValue(key, "TaskbarCat")
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        # Already removed, that's fine
        return True
    except Exception as e:
        logger.exception("Error removing from startup: %s", e)
        return False


class TaskbarCatOverlay:
    def __init__(self, app):
        self.app = app
        self.pose_images = {}
        self.pose_source_images = {}
        self.labels = []
        self.label_states = {}
        
        # Direction thresholds (in pixels)
        self.H_STRONG_THRESHOLD = 100
        self.H_WEAK_THRESHOLD = 60
        self.V_THRESHOLD = 80
        
        # Cooldown between pose changes (milliseconds)
        self.POSE_CHANGE_COOLDOWN_MS = 150
        
        # Load saved settings
        settings = load_settings()
        
        # Cat size
        self.cat_size = QtCore.QSize(settings["size"], settings["size"])
        
        # Position offsets (positive = lower/right on screen)
        self.y_offset = settings["y_offset"]
        self.x_offset = settings["x_offset"]
        self.monitor_mode = settings["monitor_mode"]
        
        # Anchor point relative to image (head is in top middle third)
        # x = width/2 (center), y = height/3 (top third)
        self.anchor_x_ratio = 0.5
        self.anchor_y_ratio = 0.33
        
        self.setup_windows()
        self.load_images()
        self.setup_timer()
        
        # Get exe path for startup management
        if getattr(sys, 'frozen', False):
            self.startup_command = f'"{sys.executable}"'
        else:
            pythonw_path = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            python_exec = pythonw_path if os.path.exists(pythonw_path) else sys.executable
            script_path = os.path.abspath(__file__)
            self.startup_command = f'"{python_exec}" "{script_path}"'
        
        self.setup_system_tray()
    
    @staticmethod
    def _configure_spin_for_typing(spin):
        """QSpinBox: no step arrows; keyboard editing in line edit."""
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        spin.setKeyboardTracking(True)
        spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        spin.setCorrectionMode(QAbstractSpinBox.CorrectionMode.CorrectToPreviousValue)
        le = spin.lineEdit()
        if le is not None:
            le.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _persist_config(self):
        save_settings(
            self.cat_size.width(),
            self.y_offset,
            self.x_offset,
            self.monitor_mode,
        )

    def _apply_tray_values_and_save(self):
        """Commit spinbox text, apply monitor mode, update overlay, write YAML."""
        if not getattr(self, "_tray_y_spin", None):
            return
        self._tray_y_spin.interpretText()
        self._tray_x_spin.interpretText()
        self._tray_size_spin.interpretText()
        self.y_offset = self._tray_y_spin.value()
        self.x_offset = self._tray_x_spin.value()
        self.cat_size = QtCore.QSize(self._tray_size_spin.value(), self._tray_size_spin.value())
        mode_changed = False
        if getattr(self, "_tray_monitor_row", None) is not None and self._tray_monitor_row.isVisible():
            mode = self._tray_monitor_combo.currentData()
            if mode != self.monitor_mode:
                self.monitor_mode = mode
                mode_changed = True
        if mode_changed:
            self.setup_windows()
        else:
            self.update_cat_position()
        self._persist_config()

    def _sync_tray_controls_from_state(self):
        """Refresh tray widgets when the menu opens."""
        if not getattr(self, "_tray_y_spin", None):
            return
        self._tray_y_spin.blockSignals(True)
        self._tray_x_spin.blockSignals(True)
        self._tray_size_spin.blockSignals(True)
        self._tray_monitor_combo.blockSignals(True)
        self._tray_startup_checkbox.blockSignals(True)

        self._tray_y_spin.setValue(self.y_offset)
        self._tray_x_spin.setValue(self.x_offset)
        self._tray_size_spin.setValue(self.cat_size.width())
        self._tray_monitor_combo.setCurrentIndex(0 if self.monitor_mode == "primary" else 1)
        self._tray_startup_checkbox.setChecked(is_startup_enabled())

        if getattr(self, "_tray_monitor_row", None) is not None:
            self._tray_monitor_row.setVisible(len(self.app.screens()) > 1)

        self._tray_y_spin.blockSignals(False)
        self._tray_x_spin.blockSignals(False)
        self._tray_size_spin.blockSignals(False)
        self._tray_monitor_combo.blockSignals(False)
        self._tray_startup_checkbox.blockSignals(False)

    def get_target_screens(self):
        """Get the target screens based on monitor mode."""
        if self.monitor_mode == "all":
            return self.app.screens()
        return [self.app.primaryScreen()]

    def create_cat_label(self):
        label = QLabel()
        label.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        label.resize(self.cat_size)
        label.show()
        self.app.processEvents()
        make_click_through(int(label.winId()))
        return label

    def setup_windows(self):
        """Create one cat window per target monitor."""
        for label in self.labels:
            label.close()

        self.labels = []
        self.label_states = {}

        for _screen in self.get_target_screens():
            label = self.create_cat_label()
            self.labels.append(label)
            self.label_states[id(label)] = {
                "current_pose": None,
                "last_change_time": 0
            }

        self.update_cat_position()
    
    def load_images(self):
        # Get the images directory (works for both dev and bundled exe)
        images_dir = get_resource_path("images")
        
        # Auto-load all cat pose images
        if os.path.exists(images_dir):
            for filename in os.listdir(images_dir):
                if filename.endswith('.png') and not filename.startswith('cat_'):
                    # Skip the ICO file and old cat_ prefixed files
                    image_path = os.path.join(images_dir, filename)
                    # Use filename without extension as pose name
                    pose_name = filename[:-4]  # Remove .png
                    
                    pixmap = QPixmap(image_path)
                    if pixmap.isNull():
                        logger.warning("Skipping invalid image: %s", image_path)
                        continue

                    self.pose_source_images[pose_name] = pixmap
                    logger.info("Loaded pose: %s", pose_name)

        self.rebuild_scaled_pose_images()
        
        # Set initial pose (prefer forward, fallback to first available)
        initial_pose = None
        if "forward" in self.pose_images:
            initial_pose = "forward"
        elif len(self.pose_images) > 0:
            initial_pose = list(self.pose_images.keys())[0]
            logger.info("Using %s as initial pose", initial_pose)

        if initial_pose:
            self.set_pose_for_all(initial_pose)

    def rebuild_scaled_pose_images(self):
        """Rebuild scaled images from in-memory originals."""
        self.pose_images.clear()
        for pose_name, pixmap in self.pose_source_images.items():
            self.pose_images[pose_name] = pixmap.scaled(
                self.cat_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
    
    def set_pose_for_label(self, label, pose_name, current_time=None):
        if pose_name not in self.pose_images:
            return

        state = self.label_states.get(id(label))
        if not state:
            return

        if pose_name == state["current_pose"]:
            return

        label.setPixmap(self.pose_images[pose_name])
        state["current_pose"] = pose_name
        state["last_change_time"] = current_time if current_time is not None else QtCore.QDateTime.currentMSecsSinceEpoch()

    def set_pose_for_all(self, pose_name):
        for label in self.labels:
            self.set_pose_for_label(label, pose_name)
    
    def get_cat_anchor_point(self, label):
        rect = label.geometry()
        anchor_x = rect.x() + int(rect.width() * self.anchor_x_ratio)
        anchor_y = rect.y() + int(rect.height() * self.anchor_y_ratio)
        return anchor_x, anchor_y
    
    def determine_direction(self, dx, dy):
        # Horizontal direction with more granular detection
        if dx < -self.H_STRONG_THRESHOLD:
            h_dir = "left"
            h_intensity = "far"
        elif dx < -self.H_WEAK_THRESHOLD:
            h_dir = "left"
            h_intensity = "normal"
        elif dx < -self.H_WEAK_THRESHOLD // 2:
            h_dir = "left"
            h_intensity = "slight"
        elif dx > self.H_STRONG_THRESHOLD:
            h_dir = "right"
            h_intensity = "far"
        elif dx > self.H_WEAK_THRESHOLD:
            h_dir = "right"
            h_intensity = "normal"
        elif dx > self.H_WEAK_THRESHOLD // 2:
            h_dir = "right"
            h_intensity = "slight"
        else:
            h_dir = "forward"
            h_intensity = "normal"
        
        # Vertical direction (note: positive dy means mouse is BELOW cat on screen)
        if dy < -self.V_THRESHOLD:
            v_dir = "up"
            v_intensity = "normal"
        elif dy < -self.V_THRESHOLD // 2:
            v_dir = "up"
            v_intensity = "slight"
        elif dy > self.V_THRESHOLD:
            v_dir = "down"
            v_intensity = "normal"
        elif dy > self.V_THRESHOLD // 2:
            v_dir = "down"
            v_intensity = "slight"
        else:
            v_dir = "center"
            v_intensity = "normal"
        
        return h_dir, h_intensity, v_dir, v_intensity
    
    def find_best_pose(self, h_dir, h_intensity, v_dir, v_intensity):
        """Find the best matching pose based on direction and intensity"""
        # Build pose name candidates in order of preference
        candidates = []
        
        # For forward direction
        if h_dir == "forward":
            if v_dir == "center":
                candidates = ["forward"]
            else:
                # Try with intensity first, then without
                if v_intensity == "slight":
                    candidates = [f"forward_slight_{v_dir}", f"forward_{v_dir}", "forward"]
                else:
                    candidates = [f"forward_{v_dir}", f"forward_slight_{v_dir}", "forward"]
        
        # For left/right directions
        elif h_dir in ["left", "right"]:
            # Handle special cases like "left_left" (far left) and "right_right" (far right)
            if h_intensity == "far":
                # Try far versions first
                if v_dir == "center":
                    candidates = [f"{h_dir}_{h_dir}", f"{h_dir}", f"{h_dir}_center"]
                else:
                    if v_intensity == "slight":
                        candidates = [
                            f"{h_dir}_slight_{v_dir}",
                            f"{h_dir}_{v_dir}",
                            f"{h_dir}_{h_dir}",
                            f"{h_dir}"
                        ]
                    else:
                        candidates = [
                            f"{h_dir}_{v_dir}",
                            f"{h_dir}_slight_{v_dir}",
                            f"{h_dir}_{h_dir}",
                            f"{h_dir}"
                        ]
            elif h_intensity == "slight":
                # Slight left/right - prefer forward_left/forward_right as inbetween poses
                if v_dir == "center":
                    candidates = [
                        f"forward_{h_dir}",
                        f"{h_dir}",
                        f"{h_dir}_center",
                        "forward"
                    ]
                else:
                    # Try forward_left/forward_right with vertical component first
                    forward_side = f"forward_{h_dir}"
                    if v_intensity == "slight":
                        candidates = [
                            f"{forward_side}_slight_{v_dir}",
                            f"{forward_side}_{v_dir}",
                            f"{forward_side}",
                            f"{h_dir}_slight_{v_dir}",
                            f"{h_dir}_{v_dir}",
                            f"{h_dir}",
                            f"forward_slight_{v_dir}",
                            f"forward_{v_dir}",
                            "forward"
                        ]
                    else:
                        candidates = [
                            f"{forward_side}_{v_dir}",
                            f"{forward_side}_slight_{v_dir}",
                            f"{forward_side}",
                            f"{h_dir}_{v_dir}",
                            f"{h_dir}_slight_{v_dir}",
                            f"{h_dir}",
                            f"forward_{v_dir}",
                            f"forward_slight_{v_dir}",
                            "forward"
                        ]
            else:
                # Normal horizontal intensity
                if v_dir == "center":
                    candidates = [f"{h_dir}", f"{h_dir}_center"]
                else:
                    if v_intensity == "slight":
                        candidates = [
                            f"{h_dir}_slight_{v_dir}",
                            f"{h_dir}_{v_dir}",
                            f"{h_dir}"
                        ]
                    else:
                        candidates = [
                            f"{h_dir}_{v_dir}",
                            f"{h_dir}_slight_{v_dir}",
                            f"{h_dir}"
                        ]
        
        # Try each candidate in order
        for candidate in candidates:
            if candidate in self.pose_images:
                return candidate
        
        # Fallback to forward if available, otherwise first available pose
        if "forward" in self.pose_images:
            return "forward"
        elif len(self.pose_images) > 0:
            return list(self.pose_images.keys())[0]
        else:
            return None
    
    def update_orientation(self):
        # Get mouse position
        mouse_x, mouse_y = get_global_mouse_pos()
        current_time = QtCore.QDateTime.currentMSecsSinceEpoch()

        for label in self.labels:
            # Get cat anchor point
            cat_x, cat_y = self.get_cat_anchor_point(label)
            
            # Calculate relative position
            dx = mouse_x - cat_x
            dy = mouse_y - cat_y
            
            # Determine direction
            h_dir, h_intensity, v_dir, v_intensity = self.determine_direction(dx, dy)
            
            # Find best available pose
            target_pose = self.find_best_pose(h_dir, h_intensity, v_dir, v_intensity)
            if target_pose is None:
                continue

            state = self.label_states.get(id(label))
            if not state:
                continue

            if target_pose != state["current_pose"]:
                time_since_last_change = current_time - state["last_change_time"]
                if time_since_last_change >= self.POSE_CHANGE_COOLDOWN_MS:
                    self.set_pose_for_label(label, target_pose, current_time=current_time)
    
    def setup_timer(self):
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_orientation)
        self.timer.start(75)  # Update every 75ms
    
    def setup_system_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray is not available")
            return

        self.tray_icon = QSystemTrayIcon(self.app)

        icon_path = get_resource_path("images/icon.ico")
        if os.path.exists(icon_path):
            icon_pixmap = QPixmap(icon_path)
            scaled_icon = icon_pixmap.scaled(
                16,
                16,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.tray_icon.setIcon(QIcon(scaled_icon))
        else:
            self.tray_icon.setIcon(
                self.app.style().standardIcon(self.app.style().StandardPixmap.SP_ComputerIcon)
            )

        menu = QMenu()
        menu.setStyleSheet(TRAY_MENU_QSS)
        menu.aboutToShow.connect(self._sync_tray_controls_from_state)

        panel = QFrame()
        panel.setObjectName("trayPanel")
        panel.setStyleSheet(TRAY_MENU_QSS)
        root = QVBoxLayout(panel)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # Row: vertical offset | horizontal offset
        row_offsets = QHBoxLayout()
        col_v = QVBoxLayout()
        col_h = QVBoxLayout()
        lbl_v = QLabel("Vertical offset")
        lbl_h = QLabel("Horizontal offset")
        self._tray_y_spin = QSpinBox()
        self._tray_y_spin.setRange(-200, 200)
        self._tray_y_spin.setValue(self.y_offset)
        self._tray_y_spin.setSuffix(" px")
        self._tray_y_spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._configure_spin_for_typing(self._tray_y_spin)

        self._tray_x_spin = QSpinBox()
        self._tray_x_spin.setRange(-500, 500)
        self._tray_x_spin.setValue(self.x_offset)
        self._tray_x_spin.setSuffix(" px")
        self._tray_x_spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._configure_spin_for_typing(self._tray_x_spin)

        col_v.addWidget(lbl_v)
        col_v.addWidget(self._tray_y_spin)
        col_h.addWidget(lbl_h)
        col_h.addWidget(self._tray_x_spin)
        row_offsets.addLayout(col_v, 1)
        row_offsets.addLayout(col_h, 1)
        root.addLayout(row_offsets)

        # Row: size
        size_row = QVBoxLayout()
        size_row.addWidget(QLabel("Size"))
        self._tray_size_spin = QSpinBox()
        self._tray_size_spin.setRange(50, 500)
        self._tray_size_spin.setValue(self.cat_size.width())
        self._tray_size_spin.setSuffix(" px")
        self._configure_spin_for_typing(self._tray_size_spin)
        size_row.addWidget(self._tray_size_spin)
        root.addLayout(size_row)

        # Row: monitor mode (hidden when only one display is connected)
        self._tray_monitor_row = QWidget()
        monitor_col = QVBoxLayout(self._tray_monitor_row)
        monitor_col.setContentsMargins(0, 0, 0, 0)
        monitor_col.setSpacing(4)
        monitor_col.addWidget(QLabel("Monitor mode"))
        self._tray_monitor_combo = QComboBox()
        self._tray_monitor_combo.addItem("Primary monitor only", "primary")
        self._tray_monitor_combo.addItem("All monitors", "all")
        self._tray_monitor_combo.setCurrentIndex(0 if self.monitor_mode == "primary" else 1)
        monitor_col.addWidget(self._tray_monitor_combo)
        self._tray_monitor_row.setVisible(len(self.app.screens()) > 1)
        root.addWidget(self._tray_monitor_row)

        # Row: start on boot | quit | save
        row_actions = QHBoxLayout()
        self._tray_startup_checkbox = QCheckBox("Start on boot")
        self._tray_startup_checkbox.setChecked(is_startup_enabled())
        quit_btn = QPushButton("Quit")
        quit_btn.setObjectName("trayQuit")
        quit_btn.clicked.connect(self.quit_application)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("traySave")
        save_btn.clicked.connect(self._apply_tray_values_and_save)
        row_actions.addWidget(self._tray_startup_checkbox, 1)
        row_actions.addWidget(quit_btn, 0)
        row_actions.addWidget(save_btn, 0)
        root.addLayout(row_actions)

        tray_action = QWidgetAction(menu)
        tray_action.setDefaultWidget(panel)
        menu.addAction(tray_action)

        def on_y_changed(v):
            self.y_offset = v
            self.update_cat_position()
            self._persist_config()

        def on_x_changed(v):
            self.x_offset = v
            self.update_cat_position()
            self._persist_config()

        def on_size_changed(v):
            self.cat_size = QtCore.QSize(v, v)
            self.update_cat_position()
            self._persist_config()

        def on_monitor_changed(_idx):
            mode = self._tray_monitor_combo.currentData()
            if mode != self.monitor_mode:
                self.monitor_mode = mode
                self.setup_windows()
                self.update_cat_position()
                self._persist_config()

        self._tray_y_spin.valueChanged.connect(on_y_changed)
        self._tray_x_spin.valueChanged.connect(on_x_changed)
        self._tray_size_spin.valueChanged.connect(on_size_changed)
        self._tray_monitor_combo.currentIndexChanged.connect(on_monitor_changed)
        self._tray_startup_checkbox.toggled.connect(self.toggle_startup)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.setToolTip("Taskbar Cat")
        self.tray_icon.show()
    
    def update_cat_position(self):
        """Update cat window position and size based on current settings"""
        screens = self.get_target_screens()
        if len(self.labels) != len(screens):
            self.setup_windows()
            return

        for label, screen in zip(self.labels, screens):
            geometry = screen.availableGeometry()
            label.resize(self.cat_size)
            x = geometry.x() + geometry.width() - self.cat_size.width() + self.x_offset
            y = geometry.y() + geometry.height() - self.cat_size.height() + self.y_offset
            label.move(x, y)
        
        # Resize all images if size changed
        current_poses = {
            id(label): self.label_states.get(id(label), {}).get("current_pose")
            for label in self.labels
        }
        self.rebuild_scaled_pose_images()
        
        # Update current pose display
        for label in self.labels:
            pose = current_poses.get(id(label))
            if pose and pose in self.pose_images:
                label.setPixmap(self.pose_images[pose])
    
    def toggle_startup(self, checked):
        """Toggle start on boot (tray checkbox)."""
        if checked:
            if add_to_startup(self.startup_command):
                return
            self._tray_startup_checkbox.blockSignals(True)
            self._tray_startup_checkbox.setChecked(False)
            self._tray_startup_checkbox.blockSignals(False)
            QMessageBox.warning(
                None,
                "Startup Error",
                "Failed to add Taskbar Cat to startup.\n\nYou may need to run as administrator.",
            )
        else:
            if remove_from_startup():
                return
            self._tray_startup_checkbox.blockSignals(True)
            self._tray_startup_checkbox.setChecked(True)
            self._tray_startup_checkbox.blockSignals(False)
            QMessageBox.warning(
                None,
                "Startup Error",
                "Failed to remove Taskbar Cat from startup.",
            )
    
    def quit_application(self):
        # Save settings before quitting
        save_settings(self.cat_size.width(), self.y_offset, self.x_offset, self.monitor_mode)
        self.timer.stop()
        self.app.quit()


def main():
    configure_logging()
    app = QApplication(sys.argv)
    
    # Ensure app doesn't exit when window is closed (since it's click-through anyway)
    app.setQuitOnLastWindowClosed(False)
    
    # Check if system tray is available
    if not QSystemTrayIcon.isSystemTrayAvailable():
        logger.warning("System tray is not available. You may need to use Task Manager to quit.")
    
    cat_overlay = TaskbarCatOverlay(app)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
