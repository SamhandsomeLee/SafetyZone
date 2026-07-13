"""#35 multi-station tabs + camera binding UI tests."""

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


def _write_two_station_config(tmp_path: Path) -> Path:
    root = Path(__file__).resolve().parents[2]
    src = root / "configs/config.example.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    # Duplicate param group + second station sharing cam0 initially.
    pg = dict(data["param_groups"][0])
    pg["id"] = "default_b"
    data["param_groups"].append(pg)
    data["stations"].append(
        {
            "id": "station1",
            "camera_id": "replay0",
            "param_group_id": "default_b",
            "detect_mode": "person",
            "enabled": True,
        }
    )
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return cfg_path


def test_multi_station_tabs_switch_preview(qapp, tmp_path: Path) -> None:
    from ui.main_window import MainWindow

    root = Path(__file__).resolve().parents[2]
    cfg_path = _write_two_station_config(tmp_path)
    engine = tmp_path / "stub.engine"
    engine.write_bytes(b"")

    win = MainWindow(
        config_path=cfg_path,
        engine_path=engine,
        project_root=root,
    )

    assert "station0" in win._station_views  # noqa: SLF001
    assert "station1" in win._station_views  # noqa: SLF001
    assert win._tabs.count() == 3  # noqa: SLF001 — overview + 2 stations

    win._activate_station("station1")  # noqa: SLF001
    assert win.current_station_id() == "station1"
    assert win._tabs.currentIndex() == win._station_tab_index["station1"]  # noqa: SLF001
    assert win._camera_panel.station_id == "station1"  # noqa: SLF001

    win._activate_station("station0")  # noqa: SLF001
    assert win.current_station_id() == "station0"


def test_bind_camera_id_for_active_station(qapp, tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox

    from core.config import load_config
    from ui.main_window import MainWindow

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args, **kwargs: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *args, **kwargs: None))

    root = Path(__file__).resolve().parents[2]
    cfg_path = _write_two_station_config(tmp_path)
    engine = tmp_path / "stub.engine"
    engine.write_bytes(b"")

    win = MainWindow(
        config_path=cfg_path,
        engine_path=engine,
        project_root=root,
    )
    win._activate_station("station1")  # noqa: SLF001

    panel = win._camera_panel  # noqa: SLF001
    for i in range(panel._cam_list.count()):  # noqa: SLF001
        item = panel._cam_list.item(i)  # noqa: SLF001
        if item is not None and item.data(Qt.ItemDataRole.UserRole) == "cam0":
            panel._cam_list.setCurrentRow(i)  # noqa: SLF001
            break

    assert panel.selected_camera_id() == "cam0"
    win._on_apply_camera_binding()  # noqa: SLF001

    reloaded = load_config(cfg_path)
    st1 = next(s for s in reloaded.stations if s.id == "station1")
    assert st1.camera_id == "cam0"
    st0 = next(s for s in reloaded.stations if s.id == "station0")
    assert st0.camera_id == "cam0"  # unchanged from example


def test_camera_panel_station_list_emits(qapp, tmp_path: Path) -> None:
    from core.config import load_config
    from ui.camera_panel import CameraPanel

    root = Path(__file__).resolve().parents[2]
    cfg_path = _write_two_station_config(tmp_path)
    config = load_config(cfg_path)

    panel = CameraPanel(config=config, project_root=root, station_id="station0")
    received: list[str] = []
    panel.station_activated.connect(received.append)

    from PySide6.QtCore import Qt

    for i in range(panel._station_list.count()):  # noqa: SLF001
        item = panel._station_list.item(i)  # noqa: SLF001
        if item is not None and item.data(Qt.ItemDataRole.UserRole) == "station1":
            panel._station_list.setCurrentRow(i)  # noqa: SLF001
            break

    assert received == ["station1"]
    assert panel.station_id == "station1"
