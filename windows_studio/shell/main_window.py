"""Three-pane Studio main window (#52 + #53 review UX).

Layout (design §8.2.2–§8.2.3):
  top   — wizard step bar
  left  — sample list + filter (全部/未确认/已确认/疑似漏检)
  center— review canvas (confirm / drag / del / add; Space cycles display)
  right — review tools or step placeholders + 勿漏标
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from windows_studio.review_ui.canvas import ReviewCanvas
from windows_studio.review_ui.display_mode import DisplayMode, display_mode_caption
from windows_studio.review_ui.editor import ReviewItem, load_workspace_review, save_review_manifest
from windows_studio.review_ui.sample_list import SampleListPanel
from windows_studio.review_ui.tools_panel import ReviewToolsPanel
from windows_studio.shell.step_bar import STEP_DEFS, WizardStepBar, WizardStepId
from windows_studio.wizard import WizardConfig, run_wizard

__all__ = ["StudioMainWindow", "WizardStepId"]

_PLACEHOLDER_HINTS: dict[WizardStepId, str] = {
    WizardStepId.INGEST: "左侧列出样本；可用「运行向导」走 CLI 同款闭环拉取难 case。",
    WizardStepId.REVIEW: "中栏：确认 / 拖框 / 删 / 补；空格切换 原图→标注→标注+预测。宁可多标、勿漏标。",
    WizardStepId.TRAIN: "右侧将显示训练进度与曲线（#54）。",
    WizardStepId.EXPORT: "导出 ONNX 并下发 Jetson inbox；验收结果展示后续增强。",
    WizardStepId.EVAL: "评估回环（召回优先 / 漏检跳转）见 #54；不替代 Jetson acceptance。",
}


class StudioMainWindow(QMainWindow):
    """AIDI-style three-column shell with review canvas (#53)."""

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

        # Left — sample list + filter
        left = QFrame()
        left.setFrameShape(QFrame.Shape.StyledPanel)
        left_layout = QVBoxLayout(left)
        self._sample_list = SampleListPanel()
        self._sample_list.selection_changed.connect(self._on_sample_selected)
        left_layout.addWidget(self._sample_list)
        splitter.addWidget(left)

        # Center — review canvas
        center = QFrame()
        center.setFrameShape(QFrame.Shape.StyledPanel)
        center_layout = QVBoxLayout(center)
        center_layout.addWidget(QLabel("画布"))
        self._canvas = ReviewCanvas()
        self._canvas.mode_changed.connect(self._on_mode_changed)
        self._canvas.item_changed.connect(self._on_item_edited)
        center_layout.addWidget(self._canvas, stretch=1)
        # Keep a hint label for non-review steps (stacked under status text area)
        self._canvas_hint = QLabel()
        self._canvas_hint.setWordWrap(True)
        self._canvas_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._canvas_hint.hide()
        center_layout.addWidget(self._canvas_hint)
        splitter.addWidget(center)

        # Right — tools
        right = QFrame()
        right.setFrameShape(QFrame.Shape.StyledPanel)
        right_layout = QVBoxLayout(right)
        self._tool_hint = QLabel()
        self._tool_hint.setWordWrap(True)
        right_layout.addWidget(self._tool_hint)

        self._review_tools = ReviewToolsPanel()
        self._review_tools.confirm_clicked.connect(self._on_confirm)
        self._review_tools.add_clicked.connect(self._on_add_box)
        self._review_tools.delete_clicked.connect(self._on_delete_box)
        self._review_tools.cycle_mode_clicked.connect(self._on_cycle_mode)
        right_layout.addWidget(self._review_tools)

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

        self.reload_review_items()
        self._on_step_selected(WizardStepId.INGEST)

    @property
    def step_bar(self) -> WizardStepBar:
        return self._step_bar

    @property
    def case_list(self):
        """Compatibility alias — underlying QListWidget."""
        return self._sample_list.list_widget

    @property
    def sample_list(self) -> SampleListPanel:
        return self._sample_list

    @property
    def canvas(self) -> ReviewCanvas:
        return self._canvas

    @property
    def canvas_hint(self) -> QLabel:
        return self._canvas_hint

    @property
    def tool_hint(self) -> QLabel:
        return self._tool_hint

    @property
    def review_tools(self) -> ReviewToolsPanel:
        return self._review_tools

    def current_step(self) -> WizardStepId:
        return self._step_bar.current()

    def set_step(self, step_id: WizardStepId) -> None:
        self._step_bar.set_current(step_id)
        self._on_step_selected(step_id)

    def reload_review_items(self) -> list[ReviewItem]:
        items = load_workspace_review(
            self._config.workspace,
            review_dir=self._config.review_dir,
            staging_dir=self._config.staging_dir,
        )
        self._sample_list.set_items(items)
        if not items:
            self._canvas.set_item(None)
            self.statusBar().showMessage("无复核样本 — 请先拉取 ingest 或加载 review 目录")
        else:
            self.statusBar().showMessage(f"已加载 {len(items)} 个样本")
        return items

    def _on_step_selected(self, step_id: WizardStepId) -> None:
        title = next(label for sid, label in STEP_DEFS if sid == step_id)
        hint = _PLACEHOLDER_HINTS.get(step_id, "")
        self._tool_hint.setText(hint)
        self._canvas_hint.setText(f"「{title}」\n\n{hint}")
        # Review tools prominent on REVIEW; still usable elsewhere for list/canvas
        self._review_tools.setVisible(step_id is WizardStepId.REVIEW)
        self.statusBar().showMessage(f"当前步骤: {title}")
        if step_id is WizardStepId.REVIEW:
            self._canvas.setFocus()

    def _on_sample_selected(self, item: ReviewItem | None) -> None:
        self._canvas.set_item(item)

    def _on_mode_changed(self, mode: DisplayMode) -> None:
        self._review_tools.set_mode_caption(mode)
        self.statusBar().showMessage(f"显示模式: {display_mode_caption(mode)}")

    def _on_item_edited(self) -> None:
        self._sample_list.refresh_labels()
        save_review_manifest(self._config.review_dir, self._sample_list.items())

    def _on_confirm(self) -> None:
        self._canvas.confirm_current()
        self._sample_list.refresh_labels()
        save_review_manifest(self._config.review_dir, self._sample_list.items())

    def _on_add_box(self) -> None:
        self._canvas.set_add_mode(True)
        self._canvas.setFocus()
        self.statusBar().showMessage("补框模式：在画布上拖拽绘制；宁可多标、勿漏标")

    def _on_delete_box(self) -> None:
        if self._canvas.delete_selected():
            self._sample_list.refresh_labels()
            save_review_manifest(self._config.review_dir, self._sample_list.items())

    def _on_cycle_mode(self) -> None:
        self._canvas.cycle_display_mode()

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
        self.reload_review_items()
        self.statusBar().showMessage(result.message)
