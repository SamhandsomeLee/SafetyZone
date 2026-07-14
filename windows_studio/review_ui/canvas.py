"""Review canvas — image + YOLO boxes with confirm / drag / del / add (#53)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from windows_studio.review_ui.display_mode import DisplayMode
from windows_studio.review_ui.editor import MISSING_LABEL_HINT, ReviewItem
from windows_studio.review_ui.labels import YoloBox, write_labels

_EMPTY_HINT = (
    "暂无样本\n\n"
    "从 workspace review/ 或 ingest 拉取后在此复核。\n"
    "宁可多标、勿漏标 — 漏标对安全系统更危险。"
)


class ReviewCanvas(QWidget):
    """Minimal AIDI-style review canvas (person boxes only; no brush/seg)."""

    item_changed = Signal()
    mode_changed = Signal(object)  # DisplayMode
    selection_changed = Signal(int)  # selected box index or -1

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(320)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setStyleSheet("background: #2a2a2a;")

        self._item: ReviewItem | None = None
        self._pixmap: QPixmap | None = None
        self._mode = DisplayMode.LABELS
        self._selected = -1
        self._add_mode = False
        self._dragging = False
        self._creating = False
        self._drag_origin = QPointF()
        self._box_origin: YoloBox | None = None
        self._rubber: QRectF | None = None
        self._img_rect = QRectF()

    @property
    def display_mode(self) -> DisplayMode:
        return self._mode

    @property
    def selected_index(self) -> int:
        return self._selected

    @property
    def add_mode(self) -> bool:
        return self._add_mode

    def set_add_mode(self, enabled: bool) -> None:
        self._add_mode = enabled
        if enabled:
            self._selected = -1
            self.selection_changed.emit(-1)
        self.update()

    def cycle_display_mode(self) -> DisplayMode:
        from windows_studio.review_ui.display_mode import next_display_mode

        self.set_display_mode(next_display_mode(self._mode))
        return self._mode

    def set_display_mode(self, mode: DisplayMode) -> None:
        if mode is self._mode:
            return
        self._mode = mode
        self.mode_changed.emit(mode)
        self.update()

    def set_item(self, item: ReviewItem | None) -> None:
        self._item = item
        self._selected = -1
        self._dragging = False
        self._creating = False
        self._rubber = None
        self._pixmap = self._load_pixmap(item) if item else None
        self.selection_changed.emit(-1)
        self.update()

    def confirm_current(self) -> None:
        if self._item is None:
            return
        self._item.confirmed = True
        self._persist()
        self.item_changed.emit()
        self.update()

    def delete_selected(self) -> bool:
        if self._item is None or self._selected < 0:
            return False
        if self._selected >= len(self._item.boxes):
            return False
        self._item.boxes.pop(self._selected)
        self._selected = -1
        self._persist()
        self.selection_changed.emit(-1)
        self.item_changed.emit()
        self.update()
        return True

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_Space:
            self.cycle_display_mode()
            event.accept()
            return
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.delete_selected():
                event.accept()
                return
        super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#2a2a2a"))

        if self._item is None:
            painter.setPen(QColor("#ddd"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, _EMPTY_HINT)
            return

        if self._pixmap is None or self._pixmap.isNull():
            painter.setPen(QColor("#ddd"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                f"{self._item.case_id}\n（无法解码图像，仍可编辑框）\n{MISSING_LABEL_HINT}",
            )
            # Synthetic canvas so boxes remain editable.
            self._img_rect = self._fit_rect(640, 480)
            painter.fillRect(self._img_rect, QColor("#404040"))
        else:
            self._img_rect = self._fit_rect(self._pixmap.width(), self._pixmap.height())
            painter.drawPixmap(self._img_rect.toRect(), self._pixmap)

        if self._mode is not DisplayMode.RAW:
            for i, box in enumerate(self._item.boxes):
                color = QColor("#22c55e") if i != self._selected else QColor("#facc15")
                self._draw_box(painter, box, color, width=2 if i != self._selected else 3)

        if self._mode is DisplayMode.LABELS_PLUS_PRED:
            for box in self._item.pred_boxes:
                self._draw_box(painter, box, QColor("#f97316"), width=2, dashed=True)

        if self._rubber is not None:
            pen = QPen(QColor("#38bdf8"), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._rubber)

        # Status strip
        flag = " · 疑似漏检" if self._item.suspect else ""
        status = "已确认" if self._item.confirmed else "未确认"
        from windows_studio.review_ui.display_mode import display_mode_caption

        caption = (
            f"{self._item.case_id} · {status}{flag} · "
            f"显示: {display_mode_caption(self._mode)} · "
            f"框 {len(self._item.boxes)}"
        )
        painter.fillRect(0, self.height() - 28, self.width(), 28, QColor(0, 0, 0, 160))
        painter.setPen(QColor("#eee"))
        painter.drawText(8, self.height() - 8, caption)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._item is None or event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        if self._add_mode:
            self._creating = True
            self._drag_origin = pos
            self._rubber = QRectF(pos, pos)
            self.update()
            return

        if self._mode is DisplayMode.RAW:
            return

        hit = self._hit_test(pos)
        self._selected = hit
        self.selection_changed.emit(hit)
        if hit >= 0:
            self._dragging = True
            self._drag_origin = pos
            self._box_origin = YoloBox(
                class_id=self._item.boxes[hit].class_id,
                cx=self._item.boxes[hit].cx,
                cy=self._item.boxes[hit].cy,
                w=self._item.boxes[hit].w,
                h=self._item.boxes[hit].h,
            )
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        if self._creating and self._rubber is not None:
            self._rubber = QRectF(self._drag_origin, pos).normalized()
            self.update()
            return
        if self._dragging and self._box_origin is not None and self._selected >= 0:
            dx = (pos.x() - self._drag_origin.x()) / max(self._img_rect.width(), 1.0)
            dy = (pos.y() - self._drag_origin.y()) / max(self._img_rect.height(), 1.0)
            box = self._box_origin
            assert self._item is not None
            self._item.boxes[self._selected] = YoloBox(
                class_id=box.class_id,
                cx=_clamp(box.cx + dx, box.w / 2, 1.0 - box.w / 2),
                cy=_clamp(box.cy + dy, box.h / 2, 1.0 - box.h / 2),
                w=box.w,
                h=box.h,
            )
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._creating and self._rubber is not None and self._item is not None:
            box = self._rect_to_yolo(self._rubber)
            if box is not None and box.w >= 0.01 and box.h >= 0.01:
                self._item.boxes.append(box)
                self._selected = len(self._item.boxes) - 1
                self._persist()
                self.selection_changed.emit(self._selected)
                self.item_changed.emit()
            self._creating = False
            self._rubber = None
            self._add_mode = False
            self.update()
            return
        if self._dragging:
            self._dragging = False
            self._box_origin = None
            self._persist()
            self.item_changed.emit()
            self.update()

    def _persist(self) -> None:
        if self._item is None:
            return
        write_labels(self._item.label_path, self._item.boxes)

    def _load_pixmap(self, item: ReviewItem) -> QPixmap | None:
        image = QImage(str(item.image_path))
        if image.isNull():
            return None
        return QPixmap.fromImage(image)

    def _fit_rect(self, iw: int, ih: int) -> QRectF:
        margin = 8
        bottom = 28
        avail_w = max(self.width() - 2 * margin, 1)
        avail_h = max(self.height() - 2 * margin - bottom, 1)
        scale = min(avail_w / iw, avail_h / ih)
        tw, th = iw * scale, ih * scale
        x = margin + (avail_w - tw) / 2
        y = margin + (avail_h - th) / 2
        return QRectF(x, y, tw, th)

    def _box_to_rect(self, box: YoloBox) -> QRectF:
        x1 = self._img_rect.left() + (box.cx - box.w / 2) * self._img_rect.width()
        y1 = self._img_rect.top() + (box.cy - box.h / 2) * self._img_rect.height()
        return QRectF(
            x1,
            y1,
            box.w * self._img_rect.width(),
            box.h * self._img_rect.height(),
        )

    def _rect_to_yolo(self, rect: QRectF) -> YoloBox | None:
        if self._img_rect.width() <= 0 or self._img_rect.height() <= 0:
            return None
        # Clip to image rect
        r = rect.intersected(self._img_rect)
        if r.width() < 2 or r.height() < 2:
            return None
        cx = (r.center().x() - self._img_rect.left()) / self._img_rect.width()
        cy = (r.center().y() - self._img_rect.top()) / self._img_rect.height()
        w = r.width() / self._img_rect.width()
        h = r.height() / self._img_rect.height()
        return YoloBox(class_id=0, cx=cx, cy=cy, w=w, h=h)

    def _draw_box(
        self,
        painter: QPainter,
        box: YoloBox,
        color: QColor,
        *,
        width: int = 2,
        dashed: bool = False,
    ) -> None:
        pen = QPen(color, width)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self._box_to_rect(box))

    def _hit_test(self, pos: QPointF) -> int:
        if self._item is None:
            return -1
        # Prefer top-most (last) box
        for i in range(len(self._item.boxes) - 1, -1, -1):
            if self._box_to_rect(self._item.boxes[i]).contains(pos):
                return i
        return -1


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
