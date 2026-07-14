"""Top wizard step bar — clickable four steps (+ eval placeholder)."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget


class WizardStepId(str, Enum):
    INGEST = "ingest"
    REVIEW = "review"
    TRAIN = "train"
    EXPORT = "export"
    EVAL = "eval"


STEP_DEFS: tuple[tuple[WizardStepId, str], ...] = (
    (WizardStepId.INGEST, "1. 拉取"),
    (WizardStepId.REVIEW, "2. 复核"),
    (WizardStepId.TRAIN, "3. 训练"),
    (WizardStepId.EXPORT, "4. 下发"),
    (WizardStepId.EVAL, "评估"),
)


class WizardStepBar(QWidget):
    """Horizontal step buttons; emits ``step_selected`` when the user clicks."""

    step_selected = Signal(object)  # WizardStepId

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: dict[WizardStepId, QPushButton] = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        for step_id, label in STEP_DEFS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setMinimumHeight(32)
            btn.clicked.connect(lambda _checked=False, s=step_id: self._on_click(s))
            layout.addWidget(btn)
            self._buttons[step_id] = btn
        layout.addStretch(1)
        self.set_current(WizardStepId.INGEST)

    def _on_click(self, step_id: WizardStepId) -> None:
        self.set_current(step_id)
        self.step_selected.emit(step_id)

    def set_current(self, step_id: WizardStepId) -> None:
        for sid, btn in self._buttons.items():
            btn.setChecked(sid == step_id)

    def current(self) -> WizardStepId:
        for sid, btn in self._buttons.items():
            if btn.isChecked():
                return sid
        return WizardStepId.INGEST
