"""Binary on/off control — QSlider QSS ignores handle height on Windows; we paint explicitly."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QSizePolicy, QWidget

TRACK = QColor("#E8E6F2")
THUMB = QColor("#7A6BA8")
THUMB_HOVER = QColor("#6B5C98")


class StartupOnBootToggle(QWidget):
    """0 = off (thumb left), 1 = on (thumb right). Same role as the old QSlider 0..1."""

    valueChanged = pyqtSignal(int)

    _MARGIN = 4
    _TRACK_H = 18
    _THUMB_W = 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._hover = False
        self.setFixedSize(88, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    def value(self) -> int:
        return self._value

    def setValue(self, v: int):
        v = 1 if v else 0
        if self._value != v:
            self._value = v
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setValue(1 - self._value)
            self.valueChanged.emit(self._value)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        w, h = self.width(), self.height()
        m = self._MARGIN
        th = self._TRACK_H
        ty = (h - th) // 2

        p.fillRect(m, ty, w - 2 * m, th, TRACK)

        tw = self._THUMB_W
        thumb_left = m if self._value == 0 else (w - m - tw)
        thumb_color = THUMB
        if self._hover:
            thumb_color = THUMB_HOVER

        p.fillRect(thumb_left, ty, tw, th, thumb_color)
