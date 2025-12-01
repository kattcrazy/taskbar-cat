import sys
import ctypes
import os
import subprocess
import winreg
import json
from PyQt6 import QtCore
from PyQt6.QtWidgets import QApplication, QLabel, QSystemTrayIcon, QMenu, QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QSpinBox, QPushButton
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt

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

def get_settings_path():
    """Get path to settings file (in same directory as exe/script)"""
    if getattr(sys, 'frozen', False):
        # Running as bundled exe
        base_path = os.path.dirname(sys.executable)
    else:
        # Running as script
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(base_path, "taskbar_cat_settings.json")

def load_settings():
    """Load saved settings from file"""
    settings_path = get_settings_path()
    default_settings = {
        "size": 150,
        "y_offset": 15,
        "x_offset": -10
    }
    
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                # Validate and merge with defaults
                result = default_settings.copy()
                if "size" in settings and 50 <= settings["size"] <= 500:
                    result["size"] = settings["size"]
                if "y_offset" in settings and -200 <= settings["y_offset"] <= 200:
                    result["y_offset"] = settings["y_offset"]
                if "x_offset" in settings and -500 <= settings["x_offset"] <= 500:
                    result["x_offset"] = settings["x_offset"]
                return result
        except Exception as e:
            print(f"Error loading settings: {e}")
            return default_settings
    
    return default_settings

def save_settings(size, y_offset, x_offset):
    """Save settings to file (skips if -testing flag is set)"""
    # Check for testing flag
    if "-testing" in sys.argv or "--testing" in sys.argv:
        return  # Don't save settings in testing mode
    
    settings_path = get_settings_path()
    settings = {
        "size": size,
        "y_offset": y_offset,
        "x_offset": x_offset
    }
    
    try:
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"Error saving settings: {e}")

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
        print(f"Error adding to startup: {e}")
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
        print(f"Error removing from startup: {e}")
        return False


class TaskbarCatOverlay:
    def __init__(self, app):
        self.app = app
        self.current_pose = None
        self.last_change_time = 0
        self.pose_images = {}
        
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
        
        # Anchor point relative to image (head is in top middle third)
        # x = width/2 (center), y = height/3 (top third)
        self.anchor_x_ratio = 0.5
        self.anchor_y_ratio = 0.33
        
        self.setup_window()
        self.load_images()
        self.setup_timer()
        
        # Get exe path for startup management
        if getattr(sys, 'frozen', False):
            self.exe_path = sys.executable
        else:
            self.exe_path = os.path.abspath(__file__)
        
        self.setup_system_tray()
    
    def setup_window(self):
        self.label = QLabel()
        self.label.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Position above taskbar, near clock (bottom-right)
        screen = self.app.primaryScreen().availableGeometry()
        self.label.resize(self.cat_size)
        x = screen.width() - self.cat_size.width() + self.x_offset
        y = screen.height() - self.cat_size.height() + self.y_offset
        self.label.move(x, y)
        
        self.label.show()
        
        # Apply click-through after window shows
        self.app.processEvents()
        self.hwnd = int(self.label.winId())
        make_click_through(self.hwnd)
    
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
                    scaled_pixmap = pixmap.scaled(
                        self.cat_size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    self.pose_images[pose_name] = scaled_pixmap
                    print(f"Loaded pose: {pose_name}")
        
        # Set initial pose (prefer forward, fallback to first available)
        if "forward" in self.pose_images:
            self.set_pose("forward")
        elif len(self.pose_images) > 0:
            first_pose = list(self.pose_images.keys())[0]
            self.set_pose(first_pose)
            print(f"Using {first_pose} as initial pose")
    
    def set_pose(self, pose_name):
        if pose_name == self.current_pose:
            return
        
        if pose_name in self.pose_images:
            self.label.setPixmap(self.pose_images[pose_name])
            self.current_pose = pose_name
            self.last_change_time = QtCore.QDateTime.currentMSecsSinceEpoch()
    
    def get_cat_anchor_point(self):
        rect = self.label.geometry()
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
        
        # Get cat anchor point
        cat_x, cat_y = self.get_cat_anchor_point()
        
        # Calculate relative position
        dx = mouse_x - cat_x
        dy = mouse_y - cat_y
        
        # Determine direction
        h_dir, h_intensity, v_dir, v_intensity = self.determine_direction(dx, dy)
        
        # Find best available pose
        target_pose = self.find_best_pose(h_dir, h_intensity, v_dir, v_intensity)
        
        if target_pose is None:
            return  # No poses available
        
        # Check cooldown
        time_since_last_change = current_time - self.last_change_time
        
        if target_pose != self.current_pose:
            if time_since_last_change >= self.POSE_CHANGE_COOLDOWN_MS:
                self.set_pose(target_pose)
    
    def setup_timer(self):
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_orientation)
        self.timer.start(75)  # Update every 75ms
    
    def setup_system_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("System tray is not available")
            return
        
        # Create system tray icon
        self.tray_icon = QSystemTrayIcon(self.app)
        
        # Use icon.ico from images folder, scaled to system tray size (16x16)
        icon_path = get_resource_path("images/icon.ico")
        if os.path.exists(icon_path):
            icon_pixmap = QPixmap(icon_path)
            # Scale to 16x16 for system tray (standard size)
            scaled_icon = icon_pixmap.scaled(
                16, 16,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.tray_icon.setIcon(QIcon(scaled_icon))
        else:
            # Fallback: create a simple icon
            self.tray_icon.setIcon(self.app.style().standardIcon(
                self.app.style().StandardPixmap.SP_ComputerIcon
            ))
        
        # Create context menu
        menu = QMenu()
        
        # Start on boot option
        self.startup_action = menu.addAction("Start on boot")
        self.startup_action.setCheckable(True)
        self.startup_action.setChecked(is_startup_enabled())
        self.startup_action.triggered.connect(self.toggle_startup)
        
        # Adjust position option
        position_action = menu.addAction("Adjust Position")
        position_action.triggered.connect(self.show_position_dialog)
        
        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_application)
        menu.addSeparator()
        uninstall_action = menu.addAction("Uninstall")
        uninstall_action.triggered.connect(self.uninstall_application)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.setToolTip("Taskbar Cat - Right-click to quit")
        self.tray_icon.show()
    
    def update_cat_position(self):
        """Update cat window position and size based on current settings"""
        screen = self.app.primaryScreen().availableGeometry()
        self.label.resize(self.cat_size)
        x = screen.width() - self.cat_size.width() + self.x_offset
        y = screen.height() - self.cat_size.height() + self.y_offset
        self.label.move(x, y)
        
        # Resize all images if size changed
        current_pose = self.current_pose
        images_dir = get_resource_path("images")
        for pose_name in list(self.pose_images.keys()):
            pose_file = f"{pose_name}.png"
            image_path = os.path.join(images_dir, pose_file)
            if os.path.exists(image_path):
                pixmap = QPixmap(image_path)
                scaled_pixmap = pixmap.scaled(
                    self.cat_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.pose_images[pose_name] = scaled_pixmap
        
        # Update current pose display
        if current_pose and current_pose in self.pose_images:
            self.label.setPixmap(self.pose_images[current_pose])
    
    def show_position_dialog(self):
        """Show dialog to adjust position and size with live preview"""
        dialog = QDialog()
        dialog.setWindowTitle("Adjust Cat Position & Size")
        dialog.setModal(True)
        
        layout = QVBoxLayout()
        
        # Instructions
        info_label = QLabel("Adjust settings - changes apply immediately")
        layout.addWidget(info_label)
        
        # Store original values for cancel
        original_y_offset = self.y_offset
        original_x_offset = self.x_offset
        original_size = self.cat_size.width()
        
        # Size control
        size_layout = QHBoxLayout()
        size_label = QLabel("Size:")
        size_spinbox = QSpinBox()
        size_spinbox.setRange(50, 500)
        size_spinbox.setValue(self.cat_size.width())
        size_spinbox.setSuffix(" px")
        size_layout.addWidget(size_label)
        size_layout.addWidget(size_spinbox)
        layout.addLayout(size_layout)
        
        # Vertical offset control
        y_layout = QHBoxLayout()
        y_label = QLabel("Vertical Offset:")
        y_spinbox = QSpinBox()
        y_spinbox.setRange(-200, 200)
        y_spinbox.setValue(self.y_offset)
        y_spinbox.setSuffix(" px")
        y_layout.addWidget(y_label)
        y_layout.addWidget(y_spinbox)
        layout.addLayout(y_layout)
        
        # Horizontal offset control
        x_layout = QHBoxLayout()
        x_label = QLabel("Horizontal Offset:")
        x_spinbox = QSpinBox()
        x_spinbox.setRange(-500, 500)
        x_spinbox.setValue(self.x_offset)
        x_spinbox.setSuffix(" px")
        x_layout.addWidget(x_label)
        x_layout.addWidget(x_spinbox)
        layout.addLayout(x_layout)
        
        # Live update functions
        def update_size(value):
            self.cat_size = QtCore.QSize(value, value)
            self.update_cat_position()
        
        def update_y_offset(value):
            self.y_offset = value
            self.update_cat_position()
        
        def update_x_offset(value):
            self.x_offset = value
            self.update_cat_position()
        
        # Connect to live updates
        size_spinbox.valueChanged.connect(update_size)
        y_spinbox.valueChanged.connect(update_y_offset)
        x_spinbox.valueChanged.connect(update_x_offset)
        
        # Buttons
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Cancel")
        
        def on_ok():
            # Save settings before closing
            save_settings(self.cat_size.width(), self.y_offset, self.x_offset)
            dialog.accept()
        
        def on_cancel():
            # Restore original values
            self.y_offset = original_y_offset
            self.x_offset = original_x_offset
            self.cat_size = QtCore.QSize(original_size, original_size)
            self.update_cat_position()
            dialog.reject()
        
        ok_button.clicked.connect(on_ok)
        cancel_button.clicked.connect(on_cancel)
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        dialog.exec()
    
    def toggle_startup(self, checked):
        """Toggle start on boot option"""
        if checked:
            # Add to startup
            if add_to_startup(self.exe_path):
                self.startup_action.setChecked(True)
            else:
                self.startup_action.setChecked(False)
                QMessageBox.warning(
                    None,
                    "Startup Error",
                    "Failed to add Taskbar Cat to startup.\n\nYou may need to run as administrator."
                )
        else:
            # Remove from startup
            if remove_from_startup():
                self.startup_action.setChecked(False)
            else:
                self.startup_action.setChecked(True)
                QMessageBox.warning(
                    None,
                    "Startup Error",
                    "Failed to remove Taskbar Cat from startup."
                )
    
    def quit_application(self):
        # Save settings before quitting
        save_settings(self.cat_size.width(), self.y_offset, self.x_offset)
        self.timer.stop()
        self.app.quit()
    
    def uninstall_application(self):
        """Uninstall the application - creates a batch script to delete the exe after closing"""
        # Remove from startup first
        remove_from_startup()
        
        # Get the path to the current executable
        if getattr(sys, 'frozen', False):
            # Running as bundled exe
            exe_path = sys.executable
        else:
            # Running as script
            exe_path = os.path.abspath(__file__)
        
        exe_dir = os.path.dirname(exe_path)
        
        # Get settings file path
        settings_path = get_settings_path()
        
        # Create a batch script to delete the exe and settings file after this process closes
        batch_script = os.path.join(exe_dir, "uninstall_taskbar_cat.bat")
        
        with open(batch_script, 'w') as f:
            f.write("@echo off\n")
            f.write("timeout /t 2 /nobreak >nul\n")  # Wait 2 seconds for app to close
            f.write(f'del /f /q "{exe_path}"\n')
            f.write(f'del /f /q "{settings_path}"\n')  # Delete settings file
            f.write(f'del /f /q "{batch_script}"\n')  # Delete itself
            f.write("exit\n")
        
        # Quit the application
        self.timer.stop()
        
        # Start the batch script (will run after this process exits)
        subprocess.Popen(['cmd.exe', '/c', batch_script], shell=False, creationflags=subprocess.CREATE_NO_WINDOW)
        
        # Small delay to ensure batch script is started, then quit
        QtCore.QTimer.singleShot(100, self.app.quit)


def main():
    app = QApplication(sys.argv)
    
    # Ensure app doesn't exit when window is closed (since it's click-through anyway)
    app.setQuitOnLastWindowClosed(False)
    
    # Check if system tray is available
    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("Warning: System tray is not available. You may need to use Task Manager to quit.")
    
    cat_overlay = TaskbarCatOverlay(app)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
