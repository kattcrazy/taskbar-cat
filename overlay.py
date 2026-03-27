import os

from PyQt6 import QtCore
from PyQt6.QtWidgets import (
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
    QSizePolicy,
)
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt

from config import load_settings, logger, save_settings
from pose_logic import determine_direction, find_best_pose
from startup import (
    add_to_startup,
    get_startup_command_string,
    is_startup_enabled,
    remove_from_startup,
)
from startup_toggle import StartupOnBootToggle
from tray_styles import TRAY_MENU_QSS, TRAY_PANEL_CONTENT_WIDTH
from win32_helpers import get_global_mouse_pos, get_resource_path, make_click_through


class TraySettingsMenu(QMenu):
    """Tray popup with QWidgetAction: default QMenu on Windows often dismisses on the first click."""

    def mousePressEvent(self, event):
        if self.childAt(event.pos()) not in (None, self):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.childAt(event.pos()) not in (None, self):
            event.accept()
            return
        super().mouseReleaseEvent(event)


class TaskbarCatOverlay:
    def __init__(self, app):
        self.app = app
        self.pose_images = {}
        self.pose_source_images = {}
        self.labels = []
        self.label_states = {}

        self.H_STRONG_THRESHOLD = 100
        self.H_WEAK_THRESHOLD = 60
        self.V_THRESHOLD = 80

        self.POSE_CHANGE_COOLDOWN_MS = 150

        settings = load_settings()

        self.cat_size = QtCore.QSize(settings["size"], settings["size"])
        self.y_offset = settings["y_offset"]
        self.x_offset = settings["x_offset"]
        self.monitor_mode = settings["monitor_mode"]

        self.anchor_x_ratio = 0.5
        self.anchor_y_ratio = 0.33

        self.setup_windows()
        self.load_images()
        self.setup_timer()

        self.startup_command = get_startup_command_string()

        self.setup_system_tray()

    @staticmethod
    def _configure_spin_for_typing(spin):
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
        if not getattr(self, "_tray_y_spin", None):
            return
        self._tray_y_spin.blockSignals(True)
        self._tray_x_spin.blockSignals(True)
        self._tray_size_spin.blockSignals(True)
        self._tray_monitor_combo.blockSignals(True)
        self._tray_startup_toggle.blockSignals(True)

        self._tray_y_spin.setValue(self.y_offset)
        self._tray_x_spin.setValue(self.x_offset)
        self._tray_size_spin.setValue(self.cat_size.width())
        self._tray_monitor_combo.setCurrentIndex(0 if self.monitor_mode == "primary" else 1)
        self._tray_startup_toggle.setValue(1 if is_startup_enabled() else 0)

        if getattr(self, "_tray_monitor_row", None) is not None:
            self._tray_monitor_row.setVisible(len(self.app.screens()) > 1)

        self._tray_y_spin.blockSignals(False)
        self._tray_x_spin.blockSignals(False)
        self._tray_size_spin.blockSignals(False)
        self._tray_monitor_combo.blockSignals(False)
        self._tray_startup_toggle.blockSignals(False)

    def get_target_screens(self):
        if self.monitor_mode == "all":
            return self.app.screens()
        return [self.app.primaryScreen()]

    def create_cat_label(self):
        label = QLabel()
        label.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        label.resize(self.cat_size)
        label.show()
        self.app.processEvents()
        make_click_through(int(label.winId()))
        return label

    def setup_windows(self):
        for label in self.labels:
            label.close()

        self.labels = []
        self.label_states = {}

        for _screen in self.get_target_screens():
            label = self.create_cat_label()
            self.labels.append(label)
            self.label_states[id(label)] = {
                "current_pose": None,
                "last_change_time": 0,
            }

        self.update_cat_position()

    def load_images(self):
        images_dir = get_resource_path("images")

        if os.path.exists(images_dir):
            for filename in os.listdir(images_dir):
                if not filename.endswith(".png"):
                    continue
                image_path = os.path.join(images_dir, filename)
                pose_name = filename[:-4]

                pixmap = QPixmap(image_path)
                if pixmap.isNull():
                    logger.warning("Skipping invalid image: %s", image_path)
                    continue

                self.pose_source_images[pose_name] = pixmap
                logger.info("Loaded pose: %s", pose_name)

        self.rebuild_scaled_pose_images()

        if not self.pose_images:
            logger.warning(
                "No pose PNGs found in %s. Add .png files (see README).",
                images_dir,
            )

        initial_pose = None
        if "forward" in self.pose_images:
            initial_pose = "forward"
        elif len(self.pose_images) > 0:
            initial_pose = list(self.pose_images.keys())[0]
            logger.info("Using %s as initial pose", initial_pose)

        if initial_pose:
            self.set_pose_for_all(initial_pose)

    def rebuild_scaled_pose_images(self):
        self.pose_images.clear()
        for pose_name, pixmap in self.pose_source_images.items():
            self.pose_images[pose_name] = pixmap.scaled(
                self.cat_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
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
        state["last_change_time"] = (
            current_time if current_time is not None else QtCore.QDateTime.currentMSecsSinceEpoch()
        )

    def set_pose_for_all(self, pose_name):
        for label in self.labels:
            self.set_pose_for_label(label, pose_name)

    def get_cat_anchor_point(self, label):
        rect = label.geometry()
        anchor_x = rect.x() + int(rect.width() * self.anchor_x_ratio)
        anchor_y = rect.y() + int(rect.height() * self.anchor_y_ratio)
        return anchor_x, anchor_y

    def update_orientation(self):
        mouse_x, mouse_y = get_global_mouse_pos()
        current_time = QtCore.QDateTime.currentMSecsSinceEpoch()

        for label in self.labels:
            cat_x, cat_y = self.get_cat_anchor_point(label)

            dx = mouse_x - cat_x
            dy = mouse_y - cat_y

            h_dir, h_intensity, v_dir, v_intensity = determine_direction(
                dx,
                dy,
                h_strong=self.H_STRONG_THRESHOLD,
                h_weak=self.H_WEAK_THRESHOLD,
                v_threshold=self.V_THRESHOLD,
            )

            target_pose = find_best_pose(
                h_dir,
                h_intensity,
                v_dir,
                v_intensity,
                self.pose_images,
            )
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
        self.timer.start(75)

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

        menu = TraySettingsMenu()
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        menu.setStyleSheet(TRAY_MENU_QSS)
        menu.aboutToShow.connect(self._sync_tray_controls_from_state)

        panel = QFrame()
        panel.setObjectName("trayPanel")
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        panel.setStyleSheet(TRAY_MENU_QSS)
        panel.setFixedWidth(TRAY_PANEL_CONTENT_WIDTH)
        panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        root = QVBoxLayout(panel)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        row_offsets = QHBoxLayout()
        row_offsets.setSpacing(10)
        col_v = QVBoxLayout()
        col_h = QVBoxLayout()
        lbl_v = QLabel("Vertical offset")
        lbl_h = QLabel("Horizontal offset")
        self._tray_y_spin = QSpinBox()
        self._tray_y_spin.setRange(-200, 200)
        self._tray_y_spin.setValue(self.y_offset)
        self._tray_y_spin.setSuffix(" px")
        self._tray_y_spin.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._configure_spin_for_typing(self._tray_y_spin)

        self._tray_x_spin = QSpinBox()
        self._tray_x_spin.setRange(-500, 500)
        self._tray_x_spin.setValue(self.x_offset)
        self._tray_x_spin.setSuffix(" px")
        self._tray_x_spin.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._configure_spin_for_typing(self._tray_x_spin)

        col_v.addWidget(lbl_v)
        col_v.addWidget(self._tray_y_spin)
        col_h.addWidget(lbl_h)
        col_h.addWidget(self._tray_x_spin)
        row_offsets.addLayout(col_v, 1)
        row_offsets.addLayout(col_h, 1)
        root.addLayout(row_offsets)

        size_row = QVBoxLayout()
        size_row.addWidget(QLabel("Size"))
        self._tray_size_spin = QSpinBox()
        self._tray_size_spin.setRange(50, 500)
        self._tray_size_spin.setValue(self.cat_size.width())
        self._tray_size_spin.setSuffix(" px")
        self._configure_spin_for_typing(self._tray_size_spin)
        size_row.addWidget(self._tray_size_spin)
        root.addLayout(size_row)

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

        startup_row = QHBoxLayout()
        startup_row.setSpacing(12)
        startup_lbl = QLabel("Start on boot")
        self._tray_startup_toggle = StartupOnBootToggle()
        self._tray_startup_toggle.setValue(1 if is_startup_enabled() else 0)
        startup_row.addWidget(startup_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        startup_row.addStretch(1)
        startup_row.addWidget(self._tray_startup_toggle, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(startup_row)

        row_actions = QHBoxLayout()
        quit_btn = QPushButton("Quit")
        quit_btn.setObjectName("trayQuit")
        quit_btn.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        quit_btn.clicked.connect(self.quit_application)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("traySave")
        save_btn.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        save_btn.clicked.connect(self._apply_tray_values_and_save)
        row_actions.setSpacing(10)
        row_actions.addStretch(1)
        row_actions.addWidget(quit_btn, 0)
        row_actions.addWidget(save_btn, 0)
        root.addLayout(row_actions)

        tray_action = QWidgetAction(menu)
        tray_action.setDefaultWidget(panel)
        menu.addAction(tray_action)

        def on_y_changed(v):
            self.y_offset = v
            self.update_cat_position()

        def on_x_changed(v):
            self.x_offset = v
            self.update_cat_position()

        def on_size_changed(v):
            self.cat_size = QtCore.QSize(v, v)
            self.update_cat_position()

        def on_monitor_changed(_idx):
            mode = self._tray_monitor_combo.currentData()
            if mode != self.monitor_mode:
                self.monitor_mode = mode
                self.setup_windows()
                self.update_cat_position()

        self._tray_y_spin.valueChanged.connect(on_y_changed)
        self._tray_x_spin.valueChanged.connect(on_x_changed)
        self._tray_size_spin.valueChanged.connect(on_size_changed)
        self._tray_monitor_combo.currentIndexChanged.connect(on_monitor_changed)
        self._tray_startup_toggle.valueChanged.connect(self._on_startup_toggle_changed)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.setToolTip("Taskbar Cat")
        self.tray_icon.show()

    def update_cat_position(self):
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

        current_poses = {
            id(label): self.label_states.get(id(label), {}).get("current_pose")
            for label in self.labels
        }
        self.rebuild_scaled_pose_images()

        for label in self.labels:
            pose = current_poses.get(id(label))
            if pose and pose in self.pose_images:
                label.setPixmap(self.pose_images[pose])

    def _on_startup_toggle_changed(self, value: int):
        self.toggle_startup(value == 1)

    def toggle_startup(self, checked):
        if checked:
            if add_to_startup(self.startup_command):
                return
            self._tray_startup_toggle.blockSignals(True)
            self._tray_startup_toggle.setValue(0)
            self._tray_startup_toggle.blockSignals(False)
            QMessageBox.warning(
                None,
                "Startup Error",
                "Failed to add Taskbar Cat to startup.\n\nYou may need to run as administrator.",
            )
        else:
            if remove_from_startup():
                return
            self._tray_startup_toggle.blockSignals(True)
            self._tray_startup_toggle.setValue(1)
            self._tray_startup_toggle.blockSignals(False)
            QMessageBox.warning(
                None,
                "Startup Error",
                "Failed to remove Taskbar Cat from startup.",
            )

    def quit_application(self):
        self.timer.stop()
        self.app.quit()
