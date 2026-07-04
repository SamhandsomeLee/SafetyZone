"""Left sidebar: camera / video source info (Bootstrap)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout, QWidget

from app.camera_source import resolve_video_path
from app.pipeline import resolve_station
from core.config import AppConfig


class CameraPanel(QWidget):
    def __init__(self, *, config: AppConfig, project_root: Path, parent=None) -> None:
        super().__init__(parent)
        station, _param = resolve_station(config, None)
        try:
            video_path = resolve_video_path(config, station, root=project_root)
            source_text = f"video_file\n{video_path.name}"
        except ValueError as exc:
            source_text = f"（无视频源）\n{exc}"

        box = QGroupBox(f"本机相机 · {station.id}")
        layout = QVBoxLayout(box)
        layout.addWidget(QLabel("Bootstrap 输入源："))
        self._source = QLabel(source_text)
        self._source.setWordWrap(True)
        layout.addWidget(self._source)
        layout.addWidget(QLabel("USB 相机绑定 → Sprint 2.2"))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        outer.addStretch(1)
