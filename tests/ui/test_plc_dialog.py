"""PLC configuration dialog tests (#32)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("PySide6")


@pytest.fixture
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _copy_example_config(tmp_path: Path) -> Path:
    root = Path(__file__).resolve().parents[2]
    src = root / "configs/config.example.json"
    cfg_path = tmp_path / "config.json"
    shutil.copy(src, cfg_path)
    return cfg_path


def test_plc_dialog_round_trip_fields(qapp, tmp_path: Path) -> None:
    from core.config import load_config
    from ui.plc_dialog import PlcConfigDialog

    cfg_path = _copy_example_config(tmp_path)
    config = load_config(cfg_path)

    dlg = PlcConfigDialog(config=config, config_path=cfg_path)
    dlg._enabled.setChecked(True)  # noqa: SLF001
    dlg._simulate.setChecked(True)  # noqa: SLF001
    dlg._ip.setText("10.0.0.5")  # noqa: SLF001
    dlg._rack.setValue(1)  # noqa: SLF001
    dlg._slot.setValue(2)  # noqa: SLF001
    dlg._db_number.setValue(12)  # noqa: SLF001
    dlg._result_offset.setValue(8)  # noqa: SLF001
    dlg._mode.setCurrentIndex(1)  # noqa: SLF001 — block
    dlg._watchdog_ms.setValue(4500)  # noqa: SLF001
    dlg._offline_hold.setChecked(False)  # noqa: SLF001
    dlg._verify_readback.setChecked(False)  # noqa: SLF001

    collected = dlg._collect_plc()  # noqa: SLF001
    assert collected.enabled is True
    assert collected.simulate is True
    assert collected.ip == "10.0.0.5"
    assert collected.rack == 1
    assert collected.slot == 2
    assert collected.db_number == 12
    assert collected.result_offset == 8
    assert collected.mode == "block"
    assert collected.watchdog_ms == 4500
    assert collected.offline_hold is False
    assert collected.verify_readback is False


def test_plc_dialog_save_writes_config(qapp, tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QDialog

    from core.config import load_config
    from ui.plc_dialog import PlcConfigDialog

    cfg_path = _copy_example_config(tmp_path)
    config = load_config(cfg_path)

    dlg = PlcConfigDialog(config=config, config_path=cfg_path)
    dlg._enabled.setChecked(True)  # noqa: SLF001
    dlg._simulate.setChecked(True)  # noqa: SLF001
    dlg._ip.setText("172.16.0.99")  # noqa: SLF001
    dlg._db_number.setValue(7)  # noqa: SLF001

    dlg._on_save()  # noqa: SLF001
    assert dlg.result() == QDialog.DialogCode.Accepted

    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data["plc"]["enabled"] is True
    assert data["plc"]["simulate"] is True
    assert data["plc"]["ip"] == "172.16.0.99"
    assert data["plc"]["db_number"] == 7

    reloaded = load_config(cfg_path)
    assert reloaded.plc.ip == "172.16.0.99"
    assert reloaded.plc.db_number == 7


def test_simulate_save_does_not_use_snap7(qapp, tmp_path: Path) -> None:
    from core.config import load_config
    from ui.plc_dialog import PlcConfigDialog

    cfg_path = _copy_example_config(tmp_path)
    config = load_config(cfg_path)

    dlg = PlcConfigDialog(config=config, config_path=cfg_path)
    dlg._simulate.setChecked(True)  # noqa: SLF001
    dlg._enabled.setChecked(False)  # noqa: SLF001

    with patch("plc.gateway.create_backend", side_effect=AssertionError("snap7 must not run")):
        dlg._on_save()  # noqa: SLF001

    saved = load_config(cfg_path)
    assert saved.plc.simulate is True


def test_main_window_plc_menu_opens_dialog(qapp, tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    from ui.main_window import MainWindow

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args, **kwargs: None))

    root = Path(__file__).resolve().parents[2]
    cfg_path = _copy_example_config(tmp_path)
    engine = tmp_path / "stub.engine"
    engine.write_bytes(b"")

    win = MainWindow(
        config_path=cfg_path,
        engine_path=engine,
        project_root=root,
    )

    opened: list[bool] = []

    class _FakeDialog:
        def __init__(self, **_kwargs) -> None:
            pass

        def exec(self) -> int:
            opened.append(True)
            return 0  # rejected

    monkeypatch.setattr("ui.main_window.PlcConfigDialog", _FakeDialog)

    menubar = win.menuBar()
    plc_menu = None
    for action in menubar.actions():
        if action.text() == "PLC":
            plc_menu = action.menu()
            break
    assert plc_menu is not None

    actions = plc_menu.actions()
    assert actions[0].text() == "PLC 配置…"
    actions[0].trigger()
    assert opened == [True]


def test_run_controller_plc_gateway_simulate(qapp, tmp_path: Path) -> None:
    from core.config import PlcConfig, load_config
    from plc.process_worker import PlcWorkerState
    from app.run_controller import RunController

    root = Path(__file__).resolve().parents[2]
    cfg_path = _copy_example_config(tmp_path)
    config = load_config(cfg_path)
    config = type(config)(  # rebuild with simulate plc
        cameras=config.cameras,
        param_groups=config.param_groups,
        stations=config.stations,
        plc=PlcConfig(enabled=False, simulate=True),
        record=config.record,
    )

    ctrl = RunController(config=config, engine_path=tmp_path / "x.engine", project_root=root)
    ctrl._start_plc_gateway(config.plc)  # noqa: SLF001
    try:
        status = ctrl._plc_gateway.wait_for_status(  # noqa: SLF001
            timeout=5.0,
            predicate=lambda s: s.state == PlcWorkerState.RUNNING,
        )
        assert status is not None
        assert status.simulate is True
        assert status.connected is True
        ctrl.write_plc_signal(2, fault=False)
        status = ctrl._plc_gateway.wait_for_status(  # noqa: SLF001
            timeout=5.0,
            predicate=lambda s: s.last_plc_int16 == 2,
        )
        assert status is not None
        assert status.last_plc_int16 == 2
    finally:
        ctrl._stop_plc_gateway()  # noqa: SLF001
