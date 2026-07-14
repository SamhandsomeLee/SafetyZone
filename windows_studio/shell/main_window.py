"""Three-pane Studio main window (#52).

Layout (design §8.2.2):
  top   — wizard step bar
  left  — case list placeholder (filters wired in #53)
  center— canvas placeholder (review canvas in #53)
  right — step tools / run wizard / status
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from windows_studio.shell.step_bar import STEP_DEFS, WizardStepBar, WizardStepId
from windows_studio.wizard import WizardConfig, run_wizard

# Re-export for callers that import from main_window.
__all__ = ["StudioMainWindow", "WizardStepId"]

_PLACEHOLDER_HINTS: dict[WizardStepId, str] = {
    WizardStepId.INGEST: "左侧将列出 outbox 难 case（#53 起可点选）。当前可用「运行向导」走 CLI 同款闭环。",
    WizardStepId.REVIEW: "中栏画布将在 #53 接入确认/改框；宁可多标、勿漏标。",
    WizardStepId.TRAIN: "右侧将显示训练进度与曲线（#54）。",
    WizardStepId.EXPORT: "导出 ONNX 并下发 Jetson inbox；验收结果展示后续增强。",
    WizardStepId.EVAL: "评估回环（召回优先 / 漏检跳转）见 #54；不替代 Jetson acceptance。",
}


class StudioMainWindow(QMainWindow):
    """AIDI-style three-column shell; step content filled in #53/#54."""

    def __init__(self, config: WizardConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("SafetyZone Windows Studio")
        self.resize(1280, 800)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        brand = QLabel("SafetyZone · Windows Studio")
        brand.setStyleSheet("font-size: 18px; font-weight: 600;")
        root_layout.addWidget(brand)

        self._step_bar = WizardStepBar()
        self._step_bar.step_selected.connect(self._on_step_selected)
        root_layout.addWidget(self._step_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left — case list
        left = QFrame()
        left.setFrameShape(QFrame.Shape.StyledPanel)
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("样本列表"))
        self._case_list = QListWidget()
        self._case_list.addItem(QListWidgetItem("（暂无样本 — #53 接 ingest/review）"))
        left_layout.addWidget(self._case_list, stretch=1)
        splitter.addWidget(left)

        # Center — canvas
        center = QFrame()
        center.setFrameShape(QFrame.Shape.StyledPanel)
        center_layout = QVBoxLayout(center)
        center_layout.addWidget(QLabel("画布"))
        self._canvas_hint = QLabel()
        self._canvas_hint.setWordWrap(True)
        self._canvas_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._canvas_hint.setMinimumHeight(320)
        self._canvas_hint.setStyleSheet(
            "background: #2a2a2a; color: #ddd; border-radius: 4px; padding: 16px;"
        )
        center_layout.addWidget(self._canvas_hint, stretch=1)
        splitter.addWidget(center)

        # Right — tools
        right = QFrame()
        right.setFrameShape(QFrame.Shape.StyledPanel)
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("步骤工具"))
        self._tool_hint = QLabel()
        self._tool_hint.setWordWrap(True)
        right_layout.addWidget(self._tool_hint)
        right_layout.addStretch(1)

        self._run_btn = QPushButton("运行向导（dry-run 默认同 CLI）")
        self._run_btn.clicked.connect(self._on_run_wizard)
        right_layout.addWidget(self._run_btn)

        recall_note = QLabel("安全提示：宁可多标、勿漏标（漏标对安全系统更危险）。")
        recall_note.setWordWrap(True)
        recall_note.setStyleSheet("color: #b45309;")
        right_layout.addWidget(recall_note)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 3)
        root_layout.addWidget(splitter, stretch=1)

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪 — 不依赖 Jetson 运行 UI")

        self._on_step_selected(WizardStepId.INGEST)

    @property
    def step_bar(self) -> WizardStepBar:
        return self._step_bar

    @property
    def case_list(self) -> QListWidget:
        return self._case_list

    @property
    def canvas_hint(self) -> QLabel:
        return self._canvas_hint

    @property
    def tool_hint(self) -> QLabel:
        return self._tool_hint

    def current_step(self) -> WizardStepId:
        return self._step_bar.current()

    def set_step(self, step_id: WizardStepId) -> None:
        self._step_bar.set_current(step_id)
        self._on_step_selected(step_id)

    def _on_step_selected(self, step_id: WizardStepId) -> None:
        title = next(label for sid, label in STEP_DEFS if sid == step_id)
        hint = _PLACEHOLDER_HINTS.get(step_id, "")
        self._canvas_hint.setText(f"「{title}」\n\n{hint}")
        self._tool_hint.setText(hint)
        self.statusBar().showMessage(f"当前步骤: {title}")

    def _on_run_wizard(self) -> None:
        self.statusBar().showMessage("向导运行中…")
        try:
            result = run_wizard(self._config)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "错误", str(exc))
            self.statusBar().showMessage(f"失败: {exc}")
            return
        if result.success:
            QMessageBox.information(self, "向导完成", result.message)
        else:
            QMessageBox.warning(self, "向导失败", result.message)
        self.statusBar().showMessage(result.message)
