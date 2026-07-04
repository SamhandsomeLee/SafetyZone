"""UI module smoke tests (no display / no TRT)."""

from __future__ import annotations

import os
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


def test_main_window_construct(qapp) -> None:
    from ui.main_window import MainWindow

    root = Path(__file__).resolve().parents[2]
    config = root / "configs/config.example.json"
    engine = root / "models/stock/yolov8s.engine"
    if not engine.is_file():
        engine.write_bytes(b"")
        try:
            win = MainWindow(
                config_path=config,
                engine_path=engine,
                project_root=root,
            )
            assert win.windowTitle().startswith("SafetyZone")
        finally:
            engine.unlink(missing_ok=True)
    else:
        win = MainWindow(
            config_path=config,
            engine_path=engine,
            project_root=root,
        )
        assert "STOCK" in win.windowTitle()
