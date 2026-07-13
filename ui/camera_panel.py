"""Left sidebar: camera list + bind camera_id for the active station (#35)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.pipeline import resolve_station
from core.config import AppConfig


class CameraPanel(QWidget):
    """List configured cameras; bind selected camera_id to the active station."""

    binding_changed = Signal(str)  # camera_id
    apply_requested = Signal()
    station_activated = Signal(str)  # station_id from left station list

    def __init__(
        self,
        *,
        config: AppConfig,
        project_root: Path,
        station_id: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._project_root = project_root
        self._config = config
        station, _param = resolve_station(config, station_id)
        self._station_id = station.id

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        st_box = QGroupBox("工位列表")
        st_layout = QVBoxLayout(st_box)
        self._station_list = QListWidget()
        self._station_list.currentItemChanged.connect(self._on_station_item_changed)
        st_layout.addWidget(self._station_list)
        outer.addWidget(st_box)

        self._cam_box = QGroupBox(f"本机相机 · {self._station_id}")
        cam_layout = QVBoxLayout(self._cam_box)
        cam_layout.addWidget(QLabel("输入源绑定："))

        self._cam_list = QListWidget()
        self._cam_list.currentItemChanged.connect(self._on_camera_item_changed)
        cam_layout.addWidget(self._cam_list)

        self._apply_btn = QPushButton("应用并保存绑定")
        self._apply_btn.clicked.connect(self.apply_requested.emit)
        cam_layout.addWidget(self._apply_btn)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        cam_layout.addWidget(self._status)
        outer.addWidget(self._cam_box, stretch=1)

        self.refresh(config)

    @property
    def station_id(self) -> str:
        return self._station_id

    def set_running(self, running: bool) -> None:
        self._cam_list.setEnabled(not running)
        self._apply_btn.setEnabled(not running)
        # Station switch still allowed while running (preview tab only).

    def selected_camera_id(self) -> str | None:
        item = self._cam_list.currentItem()
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return str(data) if data is not None else None

    def set_station(self, station_id: str, *, emit: bool = False) -> None:
        """Focus panel on *station_id* (camera binding target)."""
        if station_id == self._station_id and not emit:
            self._sync_station_list_selection()
            self._cam_box.setTitle(f"本机相机 · {self._station_id}")
            return
        self._station_id = station_id
        self._cam_box.setTitle(f"本机相机 · {self._station_id}")
        self._sync_station_list_selection()
        self.refresh(self._config)
        if emit:
            self.station_activated.emit(station_id)

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
        self._cam_box.setTitle(f"本机相机 · {self._station_id}")

        self._rebuild_station_list()
        self._rebuild_camera_list(station.camera_id)

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

    def _rebuild_station_list(self) -> None:
        self._station_list.blockSignals(True)
        self._station_list.clear()
        for st in self._config.stations:
            if not st.enabled:
                continue
            text = f"{st.id} → {st.camera_id}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, st.id)
            self._station_list.addItem(item)
        self._station_list.blockSignals(False)
        self._sync_station_list_selection()

    def _sync_station_list_selection(self) -> None:
        self._station_list.blockSignals(True)
        for i in range(self._station_list.count()):
            item = self._station_list.item(i)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == self._station_id:
                self._station_list.setCurrentRow(i)
                break
        self._station_list.blockSignals(False)

    def _rebuild_camera_list(self, bound_camera_id: str) -> None:
        self._cam_list.blockSignals(True)
        self._cam_list.clear()
        select_row = 0
        for i, cam in enumerate(self._config.cameras):
            label = cam.label or cam.id
            text = f"{cam.id} · {cam.source_type} · {label}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, cam.id)
            self._cam_list.addItem(item)
            if cam.id == bound_camera_id:
                select_row = i
        if self._cam_list.count() > 0:
            self._cam_list.setCurrentRow(select_row)
        self._cam_list.blockSignals(False)

    def _on_station_item_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        sid = current.data(Qt.ItemDataRole.UserRole)
        if sid is None:
            return
        sid_s = str(sid)
        if sid_s == self._station_id:
            return
        self._station_id = sid_s
        self._cam_box.setTitle(f"本机相机 · {self._station_id}")
        station, _ = resolve_station(self._config, self._station_id)
        self._rebuild_camera_list(station.camera_id)
        cam = next((c for c in self._config.cameras if c.id == station.camera_id), None)
        if cam is None:
            self._status.setText("未绑定相机")
        else:
            self._status.setText(f"待命：{cam.id}（{cam.source_type}）")
        self.station_activated.emit(sid_s)

    def _on_camera_item_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        cam_id = current.data(Qt.ItemDataRole.UserRole)
        if cam_id:
            self.binding_changed.emit(str(cam_id))
