"""Main window zone save wiring tests."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

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


def test_save_zones_writes_config(qapp, tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    from core.config import ParamGroup
    from ui.main_window import MainWindow

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args, **kwargs: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *args, **kwargs: None))
    root = Path(__file__).resolve().parents[2]
    src = root / "configs/config.example.json"
    cfg_path = tmp_path / "config.json"
    shutil.copy(src, cfg_path)

    engine = tmp_path / "stub.engine"
    engine.write_bytes(b"")

    win = MainWindow(
        config_path=cfg_path,
        engine_path=engine,
        project_root=root,
    )

    new_slow = [[10, 10], [500, 10], [500, 400], [10, 400]]
    new_stop = [[120, 120], [380, 120], [380, 320], [120, 320]]
    win._station_view().set_param_group(  # noqa: SLF001 — test hook
        ParamGroup(
            id="default",
            ref_width=1920,
            ref_height=1080,
            slow_polygon=new_slow,
            stop_polygon=new_stop,
        )
    )

    win._on_save_zones()  # noqa: SLF001

    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    pg = data["param_groups"][0]
    assert pg["slow_polygon"] == new_slow
    assert pg["stop_polygon"] == new_stop

    reloaded_slow, reloaded_stop = win._station_view().get_polygons()  # noqa: SLF001
    assert reloaded_slow == new_slow
    assert reloaded_stop == new_stop
