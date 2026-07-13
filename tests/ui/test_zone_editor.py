"""Zone editor unit tests (offscreen, no inference)."""

from __future__ import annotations

import os

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


def test_zone_editor_stores_ref_coordinates(qapp) -> None:
    from core.config import ParamGroup
    from ui.zone_editor import ZoneEditor

    param = ParamGroup(
        id="pg0",
        ref_width=640,
        ref_height=480,
        slow_polygon=[[10, 10], [630, 10], [630, 470], [10, 470]],
        stop_polygon=[[100, 100], [540, 100], [540, 380], [100, 380]],
    )
    editor = ZoneEditor()
    editor.resize(640, 480)
    editor.set_param_group(param)

    slow, stop = editor.get_polygons()
    assert slow == param.slow_polygon
    assert stop == param.stop_polygon
    assert editor.ref_size() == (640, 480)


def test_station_view_exposes_polygons(qapp) -> None:
    from core.config import ParamGroup
    from ui.station_view import StationView

    param = ParamGroup(
        id="pg0",
        ref_width=800,
        ref_height=600,
        slow_polygon=[[0, 0], [800, 0], [800, 600]],
        stop_polygon=[[200, 150], [600, 150], [600, 450]],
    )
    view = StationView(station_name="station0", param_group=param)
    view.resize(800, 600)

    slow, stop = view.get_polygons()
    assert slow == param.slow_polygon
    assert stop == param.stop_polygon

    view.set_param_group(
        ParamGroup(
            id="pg0",
            ref_width=800,
            ref_height=600,
            slow_polygon=[[1, 2], [3, 4], [5, 6]],
            stop_polygon=[[10, 20], [30, 40], [50, 60]],
        )
    )
    slow2, stop2 = view.get_polygons()
    assert slow2 == [[1, 2], [3, 4], [5, 6]]
    assert stop2 == [[10, 20], [30, 40], [50, 60]]
