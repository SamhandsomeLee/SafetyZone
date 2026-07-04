"""Dark industrial Qt stylesheet (Bootstrap UI)."""

from __future__ import annotations

STYLESHEET = """
QMainWindow, QWidget {
    background-color: #1e1e24;
    color: #e0e0e8;
    font-size: 13px;
}
QMenuBar {
    background-color: #2a2a32;
    color: #e0e0e8;
}
QMenuBar::item:selected {
    background-color: #4a3a6a;
}
QMenu {
    background-color: #2a2a32;
    color: #e0e0e8;
}
QToolBar {
    background-color: #252530;
    border: none;
    spacing: 6px;
    padding: 4px;
}
QToolButton, QPushButton {
    background-color: #3a3a48;
    color: #f0f0f8;
    border: 1px solid #4a4a58;
    border-radius: 4px;
    padding: 6px 12px;
    min-height: 24px;
}
QToolButton:hover, QPushButton:hover {
    background-color: #4a4a58;
}
QToolButton:disabled, QPushButton:disabled {
    color: #888898;
    background-color: #2a2a32;
}
QTabWidget::pane {
    border: 1px solid #3a3a48;
    background-color: #181820;
}
QTabBar::tab {
    background-color: #2a2a32;
    color: #c0c0d0;
    padding: 8px 16px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #4a3a6a;
    color: #ffffff;
}
QTextEdit, QPlainTextEdit {
    background-color: #121218;
    color: #b8b8c8;
    border: 1px solid #3a3a48;
    font-family: monospace;
    font-size: 12px;
}
QStatusBar {
    background-color: #252530;
    color: #c8c8d8;
}
QLabel#stockBadge {
    color: #ffb040;
    font-weight: bold;
}
QLabel#videoLabel {
    background-color: #0a0a10;
    border: 1px solid #3a3a48;
}
QGroupBox {
    border: 1px solid #3a3a48;
    margin-top: 8px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    color: #a0a0b8;
}
"""


def apply_theme(app) -> None:
    app.setStyleSheet(STYLESHEET)
