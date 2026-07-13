"""PLC configuration dialog (Wave2 #32)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.config import AppConfig, ConfigError, PlcConfig, PlcMode, save_config, validate_config
from plc.gateway import should_use_snap7


class PlcConfigDialog(QDialog):
    """Edit ``PlcConfig`` fields and persist via ``save_config``."""

    def __init__(
        self,
        *,
        config: AppConfig,
        config_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._config_path = config_path
        self._saved: PlcConfig | None = None

        self.setWindowTitle("PLC 配置")
        self.setMinimumWidth(440)

        self._enabled = QCheckBox("启用 PLC 写入")
        self._simulate = QCheckBox("仿真模式（不连 snap7）")
        self._enabled.toggled.connect(self._refresh_mode_ui)
        self._simulate.toggled.connect(self._refresh_mode_ui)

        self._ip = QLineEdit()
        self._rack = QSpinBox()
        self._rack.setRange(0, 7)
        self._slot = QSpinBox()
        self._slot.setRange(0, 31)
        self._db_number = QSpinBox()
        self._db_number.setRange(1, 65535)
        self._result_offset = QSpinBox()
        self._result_offset.setRange(0, 65534)
        self._mode = QComboBox()
        self._mode.addItem("command（命令字）", "command")
        self._mode.addItem("block（数据块）", "block")
        self._watchdog_ms = QSpinBox()
        self._watchdog_ms.setRange(500, 600_000)
        self._watchdog_ms.setSingleStep(500)
        self._offline_hold = QCheckBox("断线保持末值")
        self._verify_readback = QCheckBox("写后读回校验")

        self._conn_hint = QLabel()
        self._conn_hint.setWordWrap(True)

        self._build_ui()
        self._load_from_config(config.plc)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        mode_box = QGroupBox("运行模式")
        mode_form = QFormLayout(mode_box)
        mode_form.addRow(self._enabled)
        mode_form.addRow(self._simulate)
        root.addWidget(mode_box)

        conn_box = QGroupBox("连接参数（真机时生效）")
        conn_form = QFormLayout(conn_box)
        conn_form.addRow("IP 地址", self._ip)
        conn_form.addRow("机架 rack", self._rack)
        conn_form.addRow("槽位 slot", self._slot)
        conn_form.addRow("DB 号", self._db_number)
        conn_form.addRow("结果偏移 (byte)", self._result_offset)
        root.addWidget(conn_box)
        self._conn_box = conn_box

        adv_box = QGroupBox("高级")
        adv_form = QFormLayout(adv_box)
        adv_form.addRow("写入模式", self._mode)
        adv_form.addRow("看门狗 (ms)", self._watchdog_ms)
        adv_form.addRow(self._offline_hold)
        adv_form.addRow(self._verify_readback)
        root.addWidget(adv_box)

        root.addWidget(self._conn_hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _load_from_config(self, plc: PlcConfig) -> None:
        self._enabled.setChecked(plc.enabled)
        self._simulate.setChecked(plc.simulate)
        self._ip.setText(plc.ip)
        self._rack.setValue(plc.rack)
        self._slot.setValue(plc.slot)
        self._db_number.setValue(plc.db_number)
        self._result_offset.setValue(plc.result_offset)
        idx = self._mode.findData(plc.mode)
        self._mode.setCurrentIndex(idx if idx >= 0 else 0)
        self._watchdog_ms.setValue(plc.watchdog_ms)
        self._offline_hold.setChecked(plc.offline_hold)
        self._verify_readback.setChecked(plc.verify_readback)
        self._refresh_mode_ui()

    def _refresh_mode_ui(self, *_args: object) -> None:
        simulate = self._simulate.isChecked()
        enabled = self._enabled.isChecked()
        snap7_fields = enabled and not simulate
        self._conn_box.setEnabled(snap7_fields)
        for widget in (self._ip, self._rack, self._slot, self._db_number, self._result_offset):
            widget.setEnabled(snap7_fields)
        if simulate or not enabled:
            self._conn_hint.setText(
                "当前为仿真：保存配置不会连接 snap7，拟写入 INT16 由 SignalAdapter 映射。"
            )
        else:
            self._conn_hint.setText(
                "真机模式：检测运行时将经 Gateway 连接 PLC（现场联调请对照 checklist）。"
            )

    def _collect_plc(self) -> PlcConfig:
        mode: PlcMode = self._mode.currentData()
        return PlcConfig(
            enabled=self._enabled.isChecked(),
            simulate=self._simulate.isChecked(),
            ip=self._ip.text().strip() or "192.168.0.10",
            rack=self._rack.value(),
            slot=self._slot.value(),
            db_number=self._db_number.value(),
            result_offset=self._result_offset.value(),
            mode=mode,
            watchdog_ms=self._watchdog_ms.value(),
            offline_hold=self._offline_hold.isChecked(),
            verify_readback=self._verify_readback.isChecked(),
        )

    def plc_config(self) -> PlcConfig | None:
        """Return last saved PLC config after Accept, else None."""
        return self._saved

    def _on_save(self) -> None:
        plc = self._collect_plc()
        if should_use_snap7(plc) and not plc.ip:
            QMessageBox.warning(self, "配置无效", "真机模式需要填写 PLC IP 地址。")
            return

        updated = replace(self._config, plc=plc)
        try:
            validate_config(updated)
            save_config(updated, self._config_path)
        except (ConfigError, OSError) as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return

        self._saved = plc
        self.accept()
