"""Monitor tab: display annotated BGR frames from the inference worker."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from app.frame_bridge import FramePayload
from app.signal_display import signal_color_hex, signal_label
from core.config import ParamGroup
from ui.zone_editor import ZoneEditor, ZoneKind


def _default_param_group() -> ParamGroup:
    return ParamGroup(
        id="default",
        ref_width=640,
        ref_height=360,
        slow_polygon=[[50, 50], [590, 50], [590, 310], [50, 310]],
        stop_polygon=[[200, 100], [440, 100], [440, 260], [200, 260]],
    )


class StationView(QWidget):
    """Single-station live preview with signal readout and zone editing overlay."""

    def __init__(
        self,
        *,
        station_name: str = "station0",
        param_group: ParamGroup | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._station_name = station_name
        self._param_group = param_group or _default_param_group()

        self._video = QLabel("等待开始检测…")
        self._video.setObjectName("videoLabel")
        self._video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video.setMinimumSize(640, 360)
        self._video.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._zone_editor = ZoneEditor()
        self._zone_editor.set_param_group(self._param_group)

        preview_host = QWidget()
        preview_stack = QStackedLayout(preview_host)
        preview_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        preview_stack.addWidget(self._video)
        preview_stack.addWidget(self._zone_editor)

        self._btn_edit_slow = QPushButton("编辑 SLOW")
        self._btn_edit_slow.setCheckable(True)
        self._btn_edit_slow.setChecked(True)
        self._btn_edit_stop = QPushButton("编辑 STOP")
        self._btn_edit_stop.setCheckable(True)

        zone_group = QButtonGroup(self)
        zone_group.setExclusive(True)
        zone_group.addButton(self._btn_edit_slow)
        zone_group.addButton(self._btn_edit_stop)
        self._btn_edit_slow.toggled.connect(self._on_zone_mode_toggled)
        self._btn_edit_stop.toggled.connect(self._on_zone_mode_toggled)

        ref_w, ref_h = self._param_group.ref_width, self._param_group.ref_height
        self._ref_label = QLabel(f"参考分辨率: {ref_w}×{ref_h}（多边形坐标相对 ref）")

        zone_bar = QHBoxLayout()
        zone_bar.addWidget(self._btn_edit_slow)
        zone_bar.addWidget(self._btn_edit_stop)
        zone_bar.addStretch(1)
        zone_bar.addWidget(self._ref_label)

        self._signal_label = QLabel("signal: —")
        self._signal_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(zone_bar)
        layout.addWidget(preview_host, stretch=1)
        layout.addWidget(self._signal_label)

    def set_param_group(self, param: ParamGroup) -> None:
        self._param_group = param
        self._zone_editor.set_param_group(param)
        self._ref_label.setText(
            f"参考分辨率: {param.ref_width}×{param.ref_height}（多边形坐标相对 ref）"
        )

    def get_polygons(self) -> tuple[list[list[float]], list[list[float]]]:
        return self._zone_editor.get_polygons()

    def param_group(self) -> ParamGroup:
        slow, stop = self.get_polygons()
        return ParamGroup(
            id=self._param_group.id,
            ref_width=self._param_group.ref_width,
            ref_height=self._param_group.ref_height,
            slow_polygon=slow,
            stop_polygon=stop,
            conf=self._param_group.conf,
            enter_frames=self._param_group.enter_frames,
            exit_frames=self._param_group.exit_frames,
            hold_ms=self._param_group.hold_ms,
            min_overlap=self._param_group.min_overlap,
            nms_iou=self._param_group.nms_iou,
            min_box_area=self._param_group.min_box_area,
        )

    def _on_zone_mode_toggled(self, checked: bool) -> None:
        if not checked:
            return
        zone: ZoneKind = "slow" if self._btn_edit_slow.isChecked() else "stop"
        self._zone_editor.set_active_zone(zone)

    def update_frame(self, payload: FramePayload) -> None:
        pixmap = _numpy_bgr_to_pixmap(payload.overlay_bgr)
        if pixmap is not None:
            self._video.setPixmap(pixmap)
            h, w = payload.overlay_bgr.shape[:2]
            self._zone_editor.set_frame_size((w, h))

        label = signal_label(payload.signal, fault=payload.fault)
        color = signal_color_hex(payload.signal, fault=payload.fault)
        zone = payload.zone_hit or "—"
        self._signal_label.setText(
            f"工位 {payload.station_id}  |  signal={payload.signal} ({label})  "
            f"zone={zone}  dets={len(payload.detections)}  "
            f"{payload.infer_ms:.0f}ms  {payload.process_fps:.1f} fps"
        )
        self._signal_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def show_idle(self, message: str = "已停止") -> None:
        self._video.setText(message)
        self._video.setPixmap(QPixmap())
        ref_w, ref_h = self._param_group.ref_width, self._param_group.ref_height
        self._zone_editor.set_frame_size((ref_w, ref_h))
        self._signal_label.setText("signal: —")
        self._signal_label.setStyleSheet("")


def _numpy_bgr_to_pixmap(frame: np.ndarray) -> QPixmap | None:
    if frame is None or frame.size == 0:
        return None
    import cv2

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    bytes_per_line = ch * w
    image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(image)
