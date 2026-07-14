"""Tests for windows_studio review_ui (#41 + #53)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# Offscreen Qt for widget tests (Jetson / CI without DISPLAY).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from windows_studio.ingest import HardCase
from windows_studio.review_ui import (
    MISSING_LABEL_HINT,
    DisplayMode,
    SampleFilter,
    apply_edit_command,
    build_review_queue,
    display_mode_caption,
    filter_review_items,
    is_suspect_case,
    load_review_manifest,
    load_workspace_review,
    next_display_mode,
    read_labels,
    review_cases_batch,
    write_labels,
)


def _case(case_id: str, tmp_path: Path, *, with_label: bool, reason: str = "") -> HardCase:
    image = tmp_path / f"{case_id}.jpg"
    image.write_bytes(b"img")
    label = None
    if with_label:
        label = tmp_path / f"{case_id}.txt"
        label.write_text("0 0.5 0.5 0.2 0.3\n", encoding="utf-8")
    meta = {"reason": reason} if reason else {}
    return HardCase(case_id=case_id, image_path=image, label_path=label, metadata=meta)


def test_is_suspect_case(tmp_path: Path) -> None:
    assert is_suspect_case(HardCase("a", Path("a.jpg"), metadata={"reason": "missed_detection"}))
    assert is_suspect_case(HardCase("b", Path("b.jpg"), metadata={"score": 0.2}))
    assert is_suspect_case(HardCase("c", Path("c.jpg"), label_path=None))
    label = tmp_path / "d.txt"
    label.write_text("0 0.5 0.5 0.2 0.3\n", encoding="utf-8")
    assert not is_suspect_case(
        HardCase("d", tmp_path / "d.jpg", label_path=label, metadata={"reason": "ok"})
    )


def test_edit_confirm_add_del(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    cases = [_case("person_a", tmp_path, with_label=True)]
    items = build_review_queue(cases, review_dir)
    item = items[0]

    assert len(item.boxes) == 1
    err = apply_edit_command(item, "add 0 0.1 0.2 0.3 0.4")
    assert err is None
    assert len(item.boxes) == 2

    err = apply_edit_command(item, "edit 0 0 0.55 0.55 0.25 0.35")
    assert err is None
    assert item.boxes[0].cx == 0.55

    err = apply_edit_command(item, "del 1")
    assert err is None
    assert len(item.boxes) == 1

    err = apply_edit_command(item, "confirm")
    assert err is None
    assert item.confirmed

    write_labels(item.label_path, item.boxes)
    reloaded = read_labels(item.label_path)
    assert len(reloaded) == 1
    assert "宁可多标" in MISSING_LABEL_HINT


def test_batch_review_manifest(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    cases = [
        _case("a", tmp_path, with_label=True),
        _case("b", tmp_path, with_label=False, reason="missed_detection"),
    ]
    commands = {
        "b": ["add 0 0.5 0.5 0.2 0.3", "confirm"],
        "a": ["confirm"],
    }
    items = review_cases_batch(cases, review_dir, commands=commands)
    assert all(i.confirmed for i in items)
    assert items[1].suspect

    loaded = load_review_manifest(review_dir)
    assert len(loaded) == 2
    manifest = json.loads((review_dir / "review_manifest.json").read_text(encoding="utf-8"))
    assert manifest[0]["box_count"] >= 1


def test_filter_review_items(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    cases = [
        _case("ok", tmp_path, with_label=True),
        _case("miss", tmp_path, with_label=False, reason="missed_detection"),
    ]
    items = build_review_queue(cases, review_dir)
    items[0].confirmed = True
    assert len(filter_review_items(items, SampleFilter.ALL)) == 2
    assert [i.case_id for i in filter_review_items(items, SampleFilter.CONFIRMED)] == ["ok"]
    assert [i.case_id for i in filter_review_items(items, SampleFilter.UNCONFIRMED)] == ["miss"]
    assert [i.case_id for i in filter_review_items(items, SampleFilter.SUSPECT)] == ["miss"]


def test_display_mode_cycle() -> None:
    assert next_display_mode(DisplayMode.RAW) is DisplayMode.LABELS
    assert next_display_mode(DisplayMode.LABELS) is DisplayMode.LABELS_PLUS_PRED
    assert next_display_mode(DisplayMode.LABELS_PLUS_PRED) is DisplayMode.RAW
    assert display_mode_caption(DisplayMode.LABELS_PLUS_PRED) == "标注+预测"


def test_load_workspace_review_from_manifest(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    review_dir = workspace / "review"
    cases = [_case("seed", tmp_path, with_label=True, reason="near_zone")]
    items = review_cases_batch(cases, review_dir)
    assert items[0].suspect

    loaded = load_workspace_review(workspace)
    assert len(loaded) == 1
    assert loaded[0].case_id == "seed"


def test_load_workspace_review_empty(tmp_path: Path) -> None:
    assert load_workspace_review(tmp_path / "empty_ws") == []


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _write_png(path: Path, size: int = 64) -> None:
    from PySide6.QtGui import QColor, QImage

    img = QImage(size, size, QImage.Format.Format_RGB888)
    img.fill(QColor("#556677"))
    assert img.save(str(path), "PNG")


def test_sample_list_filter_and_canvas_mode(qapp, tmp_path: Path) -> None:
    from windows_studio.review_ui.canvas import ReviewCanvas
    from windows_studio.review_ui.sample_list import SampleListPanel
    from windows_studio.review_ui.labels import YoloBox

    review_dir = tmp_path / "review"
    review_dir.mkdir()
    img_a = tmp_path / "a.png"
    img_b = tmp_path / "b.png"
    _write_png(img_a)
    _write_png(img_b)

    items = build_review_queue(
        [
            HardCase("a", img_a, label_path=None, metadata={"reason": "ok"}),
            HardCase(
                "b",
                img_b,
                label_path=None,
                metadata={"reason": "missed_detection"},
            ),
        ],
        review_dir,
    )
    items[0].boxes = [YoloBox(0, 0.5, 0.5, 0.2, 0.2)]
    write_labels(items[0].label_path, items[0].boxes)
    items[0].confirmed = True
    items[0].suspect = False
    items[0].pred_boxes = [YoloBox(0, 0.4, 0.4, 0.15, 0.15)]

    panel = SampleListPanel()
    panel.set_items(items)
    assert len(panel.visible_items()) == 2

    panel.set_filter(SampleFilter.UNCONFIRMED)
    assert [i.case_id for i in panel.visible_items()] == ["b"]

    panel.set_filter(SampleFilter.SUSPECT)
    assert [i.case_id for i in panel.visible_items()] == ["b"]

    panel.set_filter(SampleFilter.ALL)
    panel.select_case_id("a")
    current = panel.current_item()
    assert current is not None and current.case_id == "a"

    canvas = ReviewCanvas()
    canvas.resize(400, 400)
    canvas.set_item(current)
    assert canvas.display_mode is DisplayMode.LABELS
    canvas.cycle_display_mode()
    assert canvas.display_mode is DisplayMode.LABELS_PLUS_PRED
    canvas.cycle_display_mode()
    assert canvas.display_mode is DisplayMode.RAW
    canvas.cycle_display_mode()
    assert canvas.display_mode is DisplayMode.LABELS

    canvas.confirm_current()
    assert current.confirmed


def test_shell_loads_fake_samples(qapp, tmp_path: Path) -> None:
    from windows_studio.review_ui.editor import save_review_manifest
    from windows_studio.shell import StudioMainWindow, WizardStepId
    from windows_studio.wizard import WizardConfig

    workspace = tmp_path / "ws"
    review_dir = workspace / "review"
    img = tmp_path / "case1.png"
    _write_png(img)
    cases = [
        HardCase("case1", img, metadata={"reason": "missed_detection"}),
        HardCase("case2", img, label_path=None, metadata={"reason": "ok"}),
    ]
    items = build_review_queue(cases, review_dir)
    # Give case2 a box so it is not treated as empty/suspect after queue build.
    from windows_studio.review_ui.labels import YoloBox

    items[1].boxes = [YoloBox(0, 0.5, 0.5, 0.2, 0.2)]
    write_labels(items[1].label_path, items[1].boxes)
    items[1].suspect = False
    items[1].confirmed = True
    save_review_manifest(review_dir, items)

    config = WizardConfig(workspace=workspace, dry_run=True)
    win = StudioMainWindow(config)
    assert len(win.sample_list.items()) == 2
    win.sample_list.set_filter(SampleFilter.SUSPECT)
    assert [i.case_id for i in win.sample_list.visible_items()] == ["case1"]

    win.set_step(WizardStepId.REVIEW)
    assert not win.review_tools.isHidden()
    assert "勿漏标" in MISSING_LABEL_HINT
    win.canvas.cycle_display_mode()
    assert win.canvas.display_mode is DisplayMode.LABELS_PLUS_PRED
