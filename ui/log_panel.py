"""Qt log panel for the main window."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget


class _QtLogEmitter(QObject):
    message = Signal(str)


class QtLogHandler(logging.Handler):
    """Thread-safe log handler that forwards records to a QPlainTextEdit."""

    def __init__(self, emitter: _QtLogEmitter) -> None:
        super().__init__()
        self._emitter = emitter

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._emitter.message.emit(msg)
        except Exception:  # pragma: no cover
            self.handleError(record)


class LogPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        title = QLabel("运行日志")
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(title)
        layout.addWidget(self._text)

        self._emitter = _QtLogEmitter()
        self._emitter.message.connect(self._append)
        self._handler = QtLogHandler(self._emitter)
        self._handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")
        )

    def install(self) -> None:
        root = logging.getLogger()
        root.addHandler(self._handler)
        root.setLevel(logging.INFO)

    @Slot(str)
    def _append(self, line: str) -> None:
        self._text.appendPlainText(line)
