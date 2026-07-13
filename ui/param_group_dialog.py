"""Param group editor: recall vs precision knobs (#38 / design §5.3)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.config import AppConfig, ConfigError, ParamGroup, save_config, validate_config

# Design §5.3 — recall knobs require secondary confirmation before persist.
RECALL_FIELD_NAMES: tuple[str, ...] = (
    "conf",
    "enter_frames",
    "exit_frames",
    "hold_ms",
    "min_overlap",
)

# Precision knobs may be edited without confirmation.
PRECISION_FIELD_NAMES: tuple[str, ...] = (
    "nms_iou",
    "min_box_area",
)


def recall_fields_changed(baseline: ParamGroup, candidate: ParamGroup) -> bool:
    """True when any recall-group field differs from *baseline*."""
    return any(getattr(baseline, name) != getattr(candidate, name) for name in RECALL_FIELD_NAMES)


class ParamGroupDialog(QDialog):
    """Edit a ``ParamGroup`` with recall/precision sections; persist via ``save_config``."""

    def __init__(
        self,
        *,
        config: AppConfig,
        config_path: Path,
        param_group_id: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._config_path = config_path
        self._baseline: ParamGroup | None = None
        self._saved_id: str | None = None

        self.setWindowTitle("参数组配置")
        self.setMinimumWidth(460)

        self._group_combo = QComboBox()
        for pg in config.param_groups:
            self._group_combo.addItem(pg.id, pg.id)
        self._group_combo.currentIndexChanged.connect(self._on_group_selected)

        # --- identity / polygons (read-only) ---
        self._id_label = QLabel()
        self._ref_label = QLabel()
        self._poly_label = QLabel()
        self._poly_label.setWordWrap(True)

        # --- recall group ---
        self._conf = QDoubleSpinBox()
        self._conf.setRange(0.01, 1.0)
        self._conf.setSingleStep(0.05)
        self._conf.setDecimals(3)

        self._enter_frames = QSpinBox()
        self._enter_frames.setRange(1, 120)

        self._exit_frames = QSpinBox()
        self._exit_frames.setRange(1, 600)

        self._hold_ms = QSpinBox()
        self._hold_ms.setRange(0, 60_000)
        self._hold_ms.setSingleStep(50)
        self._hold_ms.setSuffix(" ms")

        self._min_overlap = QDoubleSpinBox()
        self._min_overlap.setRange(0.0, 1.0)
        self._min_overlap.setSingleStep(0.05)
        self._min_overlap.setDecimals(3)

        # --- precision group ---
        self._nms_iou = QDoubleSpinBox()
        self._nms_iou.setRange(0.0, 1.0)
        self._nms_iou.setSingleStep(0.05)
        self._nms_iou.setDecimals(3)

        self._min_box_area = QDoubleSpinBox()
        self._min_box_area.setRange(0.0, 1_000_000.0)
        self._min_box_area.setSingleStep(50.0)
        self._min_box_area.setDecimals(1)

        self._build_ui()

        target_id = param_group_id
        if target_id is None and config.stations:
            enabled = [s for s in config.stations if s.enabled]
            if enabled:
                target_id = enabled[0].param_group_id
        if target_id is None and config.param_groups:
            target_id = config.param_groups[0].id

        idx = self._group_combo.findData(target_id) if target_id else -1
        if idx >= 0:
            self._group_combo.setCurrentIndex(idx)
        elif self._group_combo.count() > 0:
            self._group_combo.setCurrentIndex(0)
        else:
            self._baseline = None

        # Ensure load even if combo index did not change (single group).
        if self._baseline is None and self._group_combo.count() > 0:
            self._on_group_selected(self._group_combo.currentIndex())

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        pick = QGroupBox("参数组")
        pick_form = QFormLayout(pick)
        pick_form.addRow("选择", self._group_combo)
        pick_form.addRow("id", self._id_label)
        pick_form.addRow("参考分辨率", self._ref_label)
        pick_form.addRow("划区", self._poly_label)
        root.addWidget(pick)

        recall = QGroupBox("召回组（偏保守 · 改动需二次确认）")
        recall_form = QFormLayout(recall)
        recall_form.addRow("conf（置信度，调低偏召回）", self._conf)
        recall_form.addRow("enter_frames（进入确认帧）", self._enter_frames)
        recall_form.addRow("exit_frames（退出确认帧）", self._exit_frames)
        recall_form.addRow("hold_ms（漏检保持）", self._hold_ms)
        recall_form.addRow("min_overlap（重叠阈值）", self._min_overlap)
        hint = QLabel("多边形划区请用监控页划区编辑器；此处仅只读展示顶点数。")
        hint.setWordWrap(True)
        recall_form.addRow(hint)
        root.addWidget(recall)

        precision = QGroupBox("精度组（压误检 · 可直接改）")
        precision_form = QFormLayout(precision)
        precision_form.addRow("nms_iou（NMS IoU）", self._nms_iou)
        precision_form.addRow("min_box_area（最小框面积）", self._min_box_area)
        root.addWidget(precision)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def saved_param_group_id(self) -> str | None:
        return self._saved_id

    def _on_group_selected(self, index: int) -> None:
        if index < 0:
            return
        pg_id = self._group_combo.itemData(index)
        if pg_id is None:
            return
        pg = next((p for p in self._config.param_groups if p.id == pg_id), None)
        if pg is None:
            return
        self._load_from_param(pg)

    def _load_from_param(self, pg: ParamGroup) -> None:
        self._baseline = deepcopy(pg)
        self._id_label.setText(pg.id)
        self._ref_label.setText(f"{pg.ref_width} × {pg.ref_height}")
        self._poly_label.setText(
            f"slow={len(pg.slow_polygon)} 点 · stop={len(pg.stop_polygon)} 点（只读）"
        )
        self._conf.setValue(pg.conf)
        self._enter_frames.setValue(pg.enter_frames)
        self._exit_frames.setValue(pg.exit_frames)
        self._hold_ms.setValue(pg.hold_ms)
        self._min_overlap.setValue(pg.min_overlap)
        self._nms_iou.setValue(pg.nms_iou)
        self._min_box_area.setValue(pg.min_box_area)

    def _collect_param(self) -> ParamGroup:
        if self._baseline is None:
            raise ConfigError("no param group selected")
        return replace(
            self._baseline,
            conf=float(self._conf.value()),
            enter_frames=int(self._enter_frames.value()),
            exit_frames=int(self._exit_frames.value()),
            hold_ms=int(self._hold_ms.value()),
            min_overlap=float(self._min_overlap.value()),
            nms_iou=float(self._nms_iou.value()),
            min_box_area=float(self._min_box_area.value()),
            # polygons / ref / id unchanged from baseline
        )

    def _on_save(self) -> None:
        if self._baseline is None:
            QMessageBox.warning(self, "无法保存", "没有可选的参数组。")
            return
        try:
            candidate = self._collect_param()
        except ConfigError as exc:
            QMessageBox.warning(self, "配置无效", str(exc))
            return

        if recall_fields_changed(self._baseline, candidate):
            reply = QMessageBox.warning(
                self,
                "确认修改召回组",
                "召回组参数（conf / enter_frames / exit_frames / hold_ms / min_overlap）"
                "影响检出灵敏度，偏保守侧请勿轻易改动。\n\n"
                "确定要保存召回组变更吗？",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Ok:
                return

        groups = []
        for pg in self._config.param_groups:
            if pg.id == candidate.id:
                groups.append(candidate)
            else:
                groups.append(pg)
        updated = replace(self._config, param_groups=groups)
        try:
            validate_config(updated)
            save_config(updated, self._config_path)
        except (ConfigError, OSError) as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return

        self._config = updated
        self._baseline = deepcopy(candidate)
        self._saved_id = candidate.id
        self.accept()
