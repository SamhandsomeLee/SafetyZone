"""Left sidebar: camera / video source binding (Bootstrap)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.pipeline import resolve_station
from core.config import AppConfig


class CameraPanel(QWidget):
    """Bind station.camera_id among configured cameras; show effective source."""

    binding_changed = Signal(str)  # camera_id
    apply_requested = Signal()

    def __init__(self, *, config: AppConfig, project_root: Path, parent=None) -> None:
        super().__init__(parent)
        self._project_root = project_root
        self._config = config
        station, _param = resolve_station(config, None)
        self._station_id = station.id

        box = QGroupBox(f"本机相机 · {station.id}")
        layout = QVBoxLayout(box)
        layout.addWidget(QLabel("输入源绑定："))

        self._combo = QComboBox()
        self._combo.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self._combo)

        self._apply_btn = QPushButton("应用并保存绑定")
        self._apply_btn.clicked.connect(self.apply_requested.emit)
        layout.addWidget(self._apply_btn)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        outer.addStretch(1)

        self.refresh(config)

    def set_running(self, running: bool) -> None:
        self._combo.setEnabled(not running)
        self._apply_btn.setEnabled(not running)

    def selected_camera_id(self) -> str | None:
        data = self._combo.currentData()
        return str(data) if data is not None else None

    def refresh(
        self,
        config: AppConfig,
        *,
        opened_camera_id: str | None = None,
        opened_source_type: str | None = None,
        degraded: bool = False,
        message: str | None = None,
    ) -> None:
        self._config = config
        station, _ = resolve_station(config, self._station_id)
        self._station_id = station.id

        self._combo.blockSignals(True)
        self._combo.clear()
        for cam in config.cameras:
            label = cam.label or cam.id
            text = f"{cam.id} · {cam.source_type} · {label}"
            self._combo.addItem(text, cam.id)
        idx = self._combo.findData(station.camera_id)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        self._combo.blockSignals(False)

        if opened_camera_id is not None:
            kind = opened_source_type or "?"
            if degraded:
                self._status.setText(
                    f"运行中：{opened_camera_id}（{kind}）· 已降级\n{message or ''}"
                )
            else:
                self._status.setText(f"运行中：{opened_camera_id}（{kind}）")
        else:
            cam = next((c for c in config.cameras if c.id == station.camera_id), None)
            if cam is None:
                self._status.setText("未绑定相机")
            else:
                self._status.setText(f"待命：{cam.id}（{cam.source_type}）")

    def _on_combo_changed(self, _index: int) -> None:
        cam_id = self.selected_camera_id()
        if cam_id:
            self.binding_changed.emit(cam_id)
