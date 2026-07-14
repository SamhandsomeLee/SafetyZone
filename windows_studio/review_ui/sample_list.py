"""Left-pane sample list with filter combo (#53 + #54 case-id jump)."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from windows_studio.review_ui.editor import ReviewItem
from windows_studio.review_ui.filters import (
    FILTER_LABELS,
    SampleFilter,
    filter_by_case_ids,
    filter_review_items,
)


class SampleListPanel(QWidget):
    """Filterable review case list for the shell left column."""

    selection_changed = Signal(object)  # ReviewItem | None
    filter_changed = Signal(object)  # SampleFilter

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("样本列表"))

        self._filter_combo = QComboBox()
        for mode, label in FILTER_LABELS:
            self._filter_combo.addItem(label, mode)
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        layout.addWidget(self._filter_combo)

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self._list, stretch=1)

        self._all_items: list[ReviewItem] = []
        self._visible: list[ReviewItem] = []
        # Optional override from eval miss jump (#54); None = use combo filter only.
        self._case_id_override: list[str] | None = None
        self._show_empty_placeholder()

    @property
    def list_widget(self) -> QListWidget:
        return self._list

    @property
    def filter_combo(self) -> QComboBox:
        return self._filter_combo

    def current_filter(self) -> SampleFilter:
        data = self._filter_combo.currentData()
        if isinstance(data, SampleFilter):
            return data
        if isinstance(data, str):
            try:
                return SampleFilter(data)
            except ValueError:
                return SampleFilter.ALL
        return SampleFilter.ALL

    def set_filter(self, mode: SampleFilter) -> None:
        # Changing combo clears case-id override (user intentionally changed filter).
        self._case_id_override = None
        for i in range(self._filter_combo.count()):
            raw = self._filter_combo.itemData(i)
            if raw is mode or raw == mode.value:
                if self._filter_combo.currentIndex() == i:
                    # Same index → combo signal may not fire; rebuild explicitly.
                    self._rebuild()
                else:
                    self._filter_combo.setCurrentIndex(i)
                return
        # Fallback if combo signal did not fire (same index edge cases).
        self._rebuild()

    def filter_to_case_ids(self, case_ids: Sequence[str]) -> None:
        """Eval miss→review: show only these case ids (order preserved from full list)."""
        self._case_id_override = list(case_ids)
        prefer = case_ids[0] if case_ids else None
        self._rebuild(prefer_case_id=prefer)

    def clear_case_id_filter(self) -> None:
        """Drop case-id override; restore combo-based filter."""
        self._case_id_override = None
        self._rebuild()

    def case_id_override(self) -> list[str] | None:
        return list(self._case_id_override) if self._case_id_override is not None else None

    def set_items(self, items: list[ReviewItem]) -> None:
        self._all_items = list(items)
        self._rebuild()

    def items(self) -> list[ReviewItem]:
        return list(self._all_items)

    def visible_items(self) -> list[ReviewItem]:
        return list(self._visible)

    def current_item(self) -> ReviewItem | None:
        row = self._list.currentRow()
        if 0 <= row < len(self._visible):
            return self._visible[row]
        return None

    def select_case_id(self, case_id: str) -> bool:
        for i, item in enumerate(self._visible):
            if item.case_id == case_id:
                self._list.setCurrentRow(i)
                return True
        return False

    def refresh_labels(self) -> None:
        """Re-render list labels after confirm/edit without losing selection."""
        current_id = self.current_item().case_id if self.current_item() else None
        self._rebuild(prefer_case_id=current_id)

    def _on_filter_changed(self, _index: int) -> None:
        self._case_id_override = None
        self.filter_changed.emit(self.current_filter())
        self._rebuild()

    def _on_row_changed(self, row: int) -> None:
        if 0 <= row < len(self._visible):
            self.selection_changed.emit(self._visible[row])
        else:
            self.selection_changed.emit(None)

    def _rebuild(self, *, prefer_case_id: str | None = None) -> None:
        if self._case_id_override is not None:
            self._visible = filter_by_case_ids(self._all_items, self._case_id_override)
        else:
            mode = self.current_filter()
            self._visible = filter_review_items(self._all_items, mode)
        self._list.blockSignals(True)
        self._list.clear()
        if not self._visible:
            if not self._all_items:
                self._list.addItem(QListWidgetItem("（暂无样本 — 请先拉取或加载 review）"))
            else:
                self._list.addItem(QListWidgetItem("（当前过滤无匹配样本）"))
            self._list.blockSignals(False)
            self.selection_changed.emit(None)
            return

        select_row = 0
        for i, item in enumerate(self._visible):
            self._list.addItem(QListWidgetItem(_format_row(item)))
            if prefer_case_id and item.case_id == prefer_case_id:
                select_row = i
        self._list.setCurrentRow(select_row)
        self._list.blockSignals(False)
        self.selection_changed.emit(self._visible[select_row])

    def _show_empty_placeholder(self) -> None:
        self._list.clear()
        self._list.addItem(QListWidgetItem("（暂无样本 — 请先拉取或加载 review）"))


def _format_row(item: ReviewItem) -> str:
    bits = [item.case_id]
    if item.confirmed:
        bits.append("✓")
    else:
        bits.append("○")
    if item.suspect:
        bits.append("疑似漏检")
    bits.append(f"框{len(item.boxes)}")
    return " · ".join(bits)
