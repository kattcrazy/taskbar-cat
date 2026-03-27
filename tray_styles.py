# Tray panel width (keeps the menu compact; spin fields do not stretch edge-to-edge)
TRAY_PANEL_CONTENT_WIDTH = 300

# Neutral greys — no purple borders on chrome
_BORDER_SUBTLE = "#C3D4DB"
_BORDER_PANEL = "#D8DEE3"

TRAY_MENU_QSS = f"""
/* Opaque menu — transparent QMenu on Windows lets clicks dismiss the popup before
   embedded controls (toggle, spins) receive them. */
QMenu {{
    background-color: #ffffff;
    border: none;
    padding: 0px;
}}
QMenu::item {{
    padding: 0px;
    background: #ffffff;
}}
QMenu::separator {{
    height: 0px;
}}
QFrame#trayPanel {{
    background-color: #ffffff;
    color: #000000;
    border: 1px solid {_BORDER_PANEL};
    border-radius: 0px;
}}
QLabel {{
    color: #000000;
    background: transparent;
}}
QSpinBox {{
    background-color: #ffffff;
    color: #000000;
    border: 1px solid {_BORDER_SUBTLE};
    border-radius: 0px;
    padding: 6px 12px;
    min-height: 24px;
    selection-background-color: #9170ED;
    selection-color: #ffffff;
}}
QComboBox {{
    background-color: #ffffff;
    color: #000000;
    border: 1px solid {_BORDER_SUBTLE};
    border-radius: 0px;
    padding: 6px 12px;
    padding-right: 28px;
    min-height: 24px;
    selection-background-color: #9170ED;
    selection-color: #ffffff;
}}
QSpinBox:focus, QComboBox:focus {{
    border: 1px solid #8a96a0;
}}
QPushButton#trayQuit {{
    background-color: #ffffff;
    color: #000000;
    border: 1px solid {_BORDER_SUBTLE};
    border-style: solid;
    border-radius: 0px;
    padding: 8px 16px;
    min-width: 72px;
    min-height: 28px;
    outline: none;
}}
QPushButton#trayQuit:hover {{
    background-color: #eef1f4;
    color: #000000;
}}
QPushButton#traySave {{
    background-color: #9170ED;
    color: #ffffff;
    border: none;
    border-radius: 0px;
    padding: 8px 16px;
    min-width: 72px;
    min-height: 28px;
    font-weight: 600;
    outline: none;
}}
QPushButton#traySave:hover {{
    background-color: #80A9F5;
    color: #000000;
}}
QPushButton#traySave:pressed {{
    background-color: #6f52c4;
    color: #ffffff;
}}
"""
