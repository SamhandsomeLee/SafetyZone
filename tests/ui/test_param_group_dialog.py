"""Param group dialog tests (#38): recall confirm + precision direct save."""

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


def _copy_config(tmp_path: Path) -> Path:
    root = Path(__file__).resolve().parents[2]
    cfg_path = tmp_path / "config.json"
    shutil.copy(root / "configs/config.example.json", cfg_path)
    return cfg_path


def test_recall_fields_changed_helper() -> None:
    from core.config import ParamGroup
    from ui.param_group_dialog import recall_fields_changed

    base = ParamGroup(
        id="default",
        ref_width=640,
        ref_height=480,
        slow_polygon=[[0, 0], [1, 0], [1, 1]],
        stop_polygon=[[0, 0], [1, 0], [1, 1]],
        conf=0.3,
        enter_frames=2,
        exit_frames=10,
        hold_ms=400,
        min_overlap=0.1,
        nms_iou=0.45,
        min_box_area=400.0,
    )
    same_prec = ParamGroup(
        id="default",
        ref_width=640,
        ref_height=480,
        slow_polygon=base.slow_polygon,
        stop_polygon=base.stop_polygon,
        conf=0.3,
        enter_frames=2,
        exit_frames=10,
        hold_ms=400,
        min_overlap=0.1,
        nms_iou=0.55,
        min_box_area=200.0,
    )
    assert recall_fields_changed(base, same_prec) is False

    recall_edit = ParamGroup(
        id="default",
        ref_width=640,
        ref_height=480,
        slow_polygon=base.slow_polygon,
        stop_polygon=base.stop_polygon,
        conf=0.2,
        enter_frames=2,
        exit_frames=10,
        hold_ms=400,
        min_overlap=0.1,
        nms_iou=0.45,
        min_box_area=400.0,
    )
    assert recall_fields_changed(base, recall_edit) is True


def test_precision_change_saves_without_confirm(qapp, tmp_path: Path) -> None:
    from PySide6.QtWidgets import QDialog, QMessageBox

    from core.config import load_config
    from ui.param_group_dialog import ParamGroupDialog

    cfg_path = _copy_config(tmp_path)
    config = load_config(cfg_path)
    dlg = ParamGroupDialog(config=config, config_path=cfg_path, param_group_id="default")

    dlg._nms_iou.setValue(0.55)  # noqa: SLF001
    dlg._min_box_area.setValue(250.0)  # noqa: SLF001

    with patch.object(QMessageBox, "warning", side_effect=AssertionError("no confirm for precision")):
        dlg._on_save()  # noqa: SLF001

    assert dlg.result() == QDialog.DialogCode.Accepted
    reloaded = load_config(cfg_path)
    pg = next(p for p in reloaded.param_groups if p.id == "default")
    assert pg.nms_iou == pytest.approx(0.55)
    assert pg.min_box_area == pytest.approx(250.0)
    # recall untouched
    assert pg.conf == pytest.approx(0.3)


def test_recall_change_cancel_does_not_save(qapp, tmp_path: Path) -> None:
    from PySide6.QtWidgets import QDialog, QMessageBox

    from core.config import load_config
    from ui.param_group_dialog import ParamGroupDialog

    cfg_path = _copy_config(tmp_path)
    before = json.loads(cfg_path.read_text(encoding="utf-8"))
    config = load_config(cfg_path)
    dlg = ParamGroupDialog(config=config, config_path=cfg_path, param_group_id="default")

    dlg._conf.setValue(0.15)  # noqa: SLF001
    dlg._enter_frames.setValue(1)  # noqa: SLF001

    with patch.object(
        QMessageBox,
        "warning",
        return_value=QMessageBox.StandardButton.Cancel,
    ):
        dlg._on_save()  # noqa: SLF001

    assert dlg.result() != QDialog.DialogCode.Accepted
    after = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert after["param_groups"][0]["conf"] == before["param_groups"][0]["conf"]
    assert after["param_groups"][0]["enter_frames"] == before["param_groups"][0]["enter_frames"]


def test_recall_change_confirm_saves(qapp, tmp_path: Path) -> None:
    from PySide6.QtWidgets import QDialog, QMessageBox

    from core.config import load_config
    from ui.param_group_dialog import ParamGroupDialog

    cfg_path = _copy_config(tmp_path)
    config = load_config(cfg_path)
    dlg = ParamGroupDialog(config=config, config_path=cfg_path, param_group_id="default")

    dlg._conf.setValue(0.22)  # noqa: SLF001
    dlg._hold_ms.setValue(800)  # noqa: SLF001

    with patch.object(
        QMessageBox,
        "warning",
        return_value=QMessageBox.StandardButton.Ok,
    ):
        dlg._on_save()  # noqa: SLF001

    assert dlg.result() == QDialog.DialogCode.Accepted
    reloaded = load_config(cfg_path)
    pg = next(p for p in reloaded.param_groups if p.id == "default")
    assert pg.conf == pytest.approx(0.22)
    assert pg.hold_ms == 800


def test_main_window_param_menu_opens_dialog(qapp, tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    from ui.main_window import MainWindow

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args, **kwargs: None))

    root = Path(__file__).resolve().parents[2]
    cfg_path = _copy_config(tmp_path)
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
            return 0

        def saved_param_group_id(self) -> str | None:
            return None

    monkeypatch.setattr("ui.main_window.ParamGroupDialog", _FakeDialog)

    menubar = win.menuBar()
    station_menu = None
    for action in menubar.actions():
        if action.text() == "工位":
            station_menu = action.menu()
            break
    assert station_menu is not None
    assert station_menu.actions()[0].text() == "参数组…"
    station_menu.actions()[0].trigger()
    assert opened == [True]
