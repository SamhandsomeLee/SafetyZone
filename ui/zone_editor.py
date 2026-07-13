"""Interactive slow/stop polygon editor (coordinates in ParamGroup ref space)."""

from __future__ import annotations

import copy
from typing import Literal

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from core.config import ParamGroup
from core.zone import scale_polygon

ZoneKind = Literal["slow", "stop"]

SLOW_FILL = QColor(0, 200, 255, 55)
SLOW_LINE = QColor(0, 200, 255)
STOP_FILL = QColor(0, 0, 255, 70)
STOP_LINE = QColor(0, 0, 255)
ACTIVE_LINE_WIDTH = 3
INACTIVE_LINE_WIDTH = 2
HANDLE_RADIUS = 6
HIT_RADIUS = 10


def _deep_copy_polygon(poly: list[list[float]]) -> list[list[float]]:
    return [[float(x), float(y)] for x, y in poly]


class ZoneEditor(QWidget):
    """Overlay editor for slow/stop polygons; stores vertices in ref resolution."""

    polygons_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._ref_width = 640
        self._ref_height = 360
        self._frame_size: tuple[int, int] = (640, 360)
        self._slow_polygon: list[list[float]] = []
        self._stop_polygon: list[list[float]] = []
        self._active_zone: ZoneKind = "slow"
        self._edit_enabled = True

        self._drag_index: int | None = None
        self._hover_index: int | None = None

    def set_param_group(self, param: ParamGroup) -> None:
        self._ref_width = param.ref_width
        self._ref_height = param.ref_height
        self._frame_size = (param.ref_width, param.ref_height)
        self._slow_polygon = _deep_copy_polygon(param.slow_polygon)
        self._stop_polygon = _deep_copy_polygon(param.stop_polygon)
        self.update()

    def set_frame_size(self, frame_size: tuple[int, int]) -> None:
        if frame_size[0] > 0 and frame_size[1] > 0:
            self._frame_size = frame_size
            self.update()

    def set_active_zone(self, zone: ZoneKind) -> None:
        self._active_zone = zone
        self._drag_index = None
        self._hover_index = None
        self.update()

    def active_zone(self) -> ZoneKind:
        return self._active_zone

    def set_edit_enabled(self, enabled: bool) -> None:
        self._edit_enabled = enabled
        if not enabled:
            self._drag_index = None
        self.update()

    def get_polygons(self) -> tuple[list[list[float]], list[list[float]]]:
        return (
            _deep_copy_polygon(self._slow_polygon),
            _deep_copy_polygon(self._stop_polygon),
        )

    def ref_size(self) -> tuple[int, int]:
        return (self._ref_width, self._ref_height)

    def _display_rect(self) -> QRectF:
        fw, fh = self._frame_size
        if fw <= 0 or fh <= 0:
            return QRectF()
        ww = float(self.width())
        wh = float(self.height())
        if ww <= 0 or wh <= 0:
            return QRectF()
        scale = min(ww / fw, wh / fh)
        dw = fw * scale
        dh = fh * scale
        x = (ww - dw) / 2.0
        y = (wh - dh) / 2.0
        return QRectF(x, y, dw, dh)

    def _ref_to_widget(self, point: tuple[float, float]) -> QPointF:
        rect = self._display_rect()
        if rect.isEmpty():
            return QPointF()
        frame_w, frame_h = self._frame_size
        ref_size = (self._ref_width, self._ref_height)
        scaled = scale_polygon([point], ref_size, (frame_w, frame_h))[0]
        wx = rect.x() + float(scaled[0]) * rect.width() / frame_w
        wy = rect.y() + float(scaled[1]) * rect.height() / frame_h
        return QPointF(wx, wy)

    def _widget_to_ref(self, pos: QPointF) -> tuple[float, float]:
        rect = self._display_rect()
        if rect.isEmpty():
            return (0.0, 0.0)
        frame_w, frame_h = self._frame_size
        fx = (pos.x() - rect.x()) / rect.width() * frame_w
        fy = (pos.y() - rect.y()) / rect.height() * frame_h
        rx = fx * self._ref_width / frame_w
        ry = fy * self._ref_height / frame_h
        return (float(rx), float(ry))

    def _active_polygon(self) -> list[list[float]]:
        return self._slow_polygon if self._active_zone == "slow" else self._stop_polygon

    def _nearest_vertex(self, pos: QPointF, polygon: list[list[float]]) -> int | None:
        best_i: int | None = None
        best_d = HIT_RADIUS * HIT_RADIUS
        for i, pt in enumerate(polygon):
            wp = self._ref_to_widget((pt[0], pt[1]))
            dx = pos.x() - wp.x()
            dy = pos.y() - wp.y()
            d2 = dx * dx + dy * dy
            if d2 <= best_d:
                best_d = d2
                best_i = i
        return best_i

    def _clamp_ref_point(self, point: tuple[float, float]) -> tuple[float, float]:
        x = max(0.0, min(float(self._ref_width), point[0]))
        y = max(0.0, min(float(self._ref_height), point[1]))
        return (x, y)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._paint_zone(painter, self._slow_polygon, "slow")
        self._paint_zone(painter, self._stop_polygon, "stop")

        if self._edit_enabled:
            self._paint_handles(painter, self._active_polygon())

    def _paint_zone(
        self,
        painter: QPainter,
        polygon: list[list[float]],
        kind: ZoneKind,
    ) -> None:
        if len(polygon) < 3:
            return
        points = [self._ref_to_widget((pt[0], pt[1])) for pt in polygon]
        active = kind == self._active_zone
        fill = SLOW_FILL if kind == "slow" else STOP_FILL
        line = SLOW_LINE if kind == "slow" else STOP_LINE
        width = ACTIVE_LINE_WIDTH if active else INACTIVE_LINE_WIDTH

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(fill))
        painter.drawPolygon(points)

        pen = QPen(line, width)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        closed = points + [points[0]]
        for i in range(len(closed) - 1):
            painter.drawLine(closed[i], closed[i + 1])

        if active and self._edit_enabled:
            label = "SLOW" if kind == "slow" else "STOP"
            painter.setPen(line)
            painter.drawText(points[0] + QPointF(6, -6), label)

    def _paint_handles(self, painter: QPainter, polygon: list[list[float]]) -> None:
        for i, pt in enumerate(polygon):
            wp = self._ref_to_widget((pt[0], pt[1]))
            color = QColor(255, 255, 255)
            if i == self._drag_index or i == self._hover_index:
                color = QColor(255, 220, 80)
            painter.setPen(QPen(QColor(20, 20, 30), 2))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(wp, HANDLE_RADIUS, HANDLE_RADIUS)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._edit_enabled or event.button() not in (
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.RightButton,
        ):
            return

        pos = event.position()
        poly = self._active_polygon()

        if event.button() == Qt.MouseButton.RightButton:
            idx = self._nearest_vertex(pos, poly)
            if idx is not None and len(poly) > 3:
                poly.pop(idx)
                self.polygons_changed.emit()
                self.update()
            return

        idx = self._nearest_vertex(pos, poly)
        if idx is not None:
            self._drag_index = idx
            return

        if event.button() == Qt.MouseButton.LeftButton:
            ref_pt = self._clamp_ref_point(self._widget_to_ref(pos))
            poly.append([ref_pt[0], ref_pt[1]])
            self._drag_index = len(poly) - 1
            self.polygons_changed.emit()
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._edit_enabled:
            return
        pos = event.position()
        poly = self._active_polygon()

        if self._drag_index is not None and 0 <= self._drag_index < len(poly):
            ref_pt = self._clamp_ref_point(self._widget_to_ref(pos))
            poly[self._drag_index] = [ref_pt[0], ref_pt[1]]
            self.polygons_changed.emit()
            self.update()
            return

        self._hover_index = self._nearest_vertex(pos, poly)
        self.update()

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:  # noqa: N802
        self._drag_index = None
        self.update()

    def leaveEvent(self, _event) -> None:  # noqa: N802
        self._hover_index = None
        self.update()
