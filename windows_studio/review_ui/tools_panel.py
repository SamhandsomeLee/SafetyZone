"""Right-pane review tool buttons (#53)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from windows_studio.review_ui.display_mode import DisplayMode, display_mode_caption
from windows_studio.review_ui.editor import MISSING_LABEL_HINT


class ReviewToolsPanel(QWidget):
    """Confirm / add / delete / display-mode controls + 勿漏标 copy."""

    confirm_clicked = Signal()
    add_clicked = Signal()
    delete_clicked = Signal()
    cycle_mode_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("复核工具"))

        self._confirm_btn = QPushButton("确认（当前样本）")
        self._confirm_btn.clicked.connect(self.confirm_clicked.emit)
        layout.addWidget(self._confirm_btn)

        self._add_btn = QPushButton("补框（拖拽绘制）")
        self._add_btn.clicked.connect(self.add_clicked.emit)
        layout.addWidget(self._add_btn)

        self._del_btn = QPushButton("删框（选中）")
        self._del_btn.clicked.connect(self.delete_clicked.emit)
        layout.addWidget(self._del_btn)

        self._mode_btn = QPushButton("显示模式（空格）")
        self._mode_btn.clicked.connect(self.cycle_mode_clicked.emit)
        layout.addWidget(self._mode_btn)

        self._mode_label = QLabel(f"当前: {display_mode_caption(DisplayMode.LABELS)}")
        self._mode_label.setWordWrap(True)
        layout.addWidget(self._mode_label)

        hint = QLabel(MISSING_LABEL_HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #b45309;")
        layout.addWidget(hint)

        layout.addStretch(1)

    def set_mode_caption(self, mode: DisplayMode) -> None:
        self._mode_label.setText(f"当前: {display_mode_caption(mode)}（空格切换）")
