"""Eval GUI: recall-first metrics + missed-case jump to review (#54)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from windows_studio.eval_ui.metrics import EvalMetrics, mock_eval_metrics


class EvalPanel(QWidget):
    """Right-pane evaluation: big recall, precision, clickable miss list."""

    jump_to_miss = Signal(str)  # case_id
    jump_to_all_misses = Signal(object)  # list[str]
    status_message = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._metrics: EvalMetrics | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("评估回环")
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(title)

        self._recall_label = QLabel("召回 —")
        self._recall_label.setStyleSheet(
            "font-size: 36px; font-weight: 700; color: #b45309;"
        )
        self._recall_label.setWordWrap(True)
        layout.addWidget(self._recall_label)

        self._precision_label = QLabel("精确率 —")
        self._precision_label.setStyleSheet("font-size: 16px; color: #334155;")
        layout.addWidget(self._precision_label)

        self._split_label = QLabel("")
        self._split_label.setWordWrap(True)
        self._split_label.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(self._split_label)

        self._gate_note = QLabel(
            "⚠️ 不替代 Jetson acceptance（场内冻结集召回闸仍在边缘机）。"
        )
        self._gate_note.setWordWrap(True)
        self._gate_note.setStyleSheet("color: #b91c1c; font-size: 12px;")
        layout.addWidget(self._gate_note)

        layout.addWidget(QLabel("漏检样本（点击 → 复核并过滤）"))
        self._miss_list = QListWidget()
        self._miss_list.itemClicked.connect(self._on_miss_clicked)
        layout.addWidget(self._miss_list, stretch=1)

        self._jump_all_btn = QPushButton("全部漏检 → 复核")
        self._jump_all_btn.clicked.connect(self._on_jump_all)
        layout.addWidget(self._jump_all_btn)

        self._reload_btn = QPushButton("加载 mock 指标")
        self._reload_btn.clicked.connect(self.load_mock)
        layout.addWidget(self._reload_btn)

        layout.addStretch(1)

    @property
    def metrics(self) -> EvalMetrics | None:
        return self._metrics

    @property
    def miss_list(self) -> QListWidget:
        return self._miss_list

    @property
    def recall_label(self) -> QLabel:
        return self._recall_label

    def set_metrics(self, metrics: EvalMetrics) -> None:
        self._metrics = metrics
        self._recall_label.setText(f"召回 {metrics.recall * 100:.1f}%")
        self._precision_label.setText(f"精确率 {metrics.precision * 100:.1f}%")
        mock_tag = " · mock" if metrics.is_mock else ""
        self._split_label.setText(f"{metrics.split}{mock_tag}\n{metrics.note}")
        self._miss_list.clear()
        if not metrics.missed_case_ids:
            self._miss_list.addItem(QListWidgetItem("（无漏检）"))
        else:
            for cid in metrics.missed_case_ids:
                self._miss_list.addItem(QListWidgetItem(cid))
        self.status_message.emit(
            f"评估已加载（召回 {metrics.recall * 100:.1f}%）— 不替代 Jetson acceptance"
        )

    def load_mock(self, case_ids: list[str] | None = None) -> None:
        # Qt clicked may pass a bool; ignore non-list.
        ids = case_ids if isinstance(case_ids, list) else None
        self.set_metrics(mock_eval_metrics(ids))

    def _on_miss_clicked(self, item: QListWidgetItem) -> None:
        text = item.text().strip()
        if not text or text.startswith("（"):
            return
        self.jump_to_miss.emit(text)

    def _on_jump_all(self) -> None:
        if self._metrics is None or not self._metrics.missed_case_ids:
            self.status_message.emit("无漏检可跳转")
            return
        self.jump_to_all_misses.emit(list(self._metrics.missed_case_ids))
