"""Monitor tab: display annotated BGR frames from the inference worker."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.frame_bridge import FramePayload
from app.signal_display import signal_color_hex, signal_label


class StationView(QWidget):
    """Single-station live preview with signal readout."""

    def __init__(self, *, station_name: str = "station0", parent=None) -> None:
        super().__init__(parent)
        self._station_name = station_name

        self._video = QLabel("等待开始检测…")
        self._video.setObjectName("videoLabel")
        self._video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video.setMinimumSize(640, 360)
        self._video.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._signal_label = QLabel("signal: —")
        self._signal_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._video, stretch=1)
        layout.addWidget(self._signal_label)

    def update_frame(self, payload: FramePayload) -> None:
        pixmap = _numpy_bgr_to_pixmap(payload.overlay_bgr)
        if pixmap is not None:
            scaled = pixmap.scaled(
                self._video.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._video.setPixmap(scaled)

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
