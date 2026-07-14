"""Tests for windows_studio train progress + eval_ui (#54)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from windows_studio.eval_ui import EvalMetrics, metrics_from_counts, mock_eval_metrics
from windows_studio.train import (
    InterruptibleTrainSession,
    TrainConfig,
    TrainProgress,
    format_eta,
)


def _minimal_dataset(tmp_path: Path) -> Path:
    images = tmp_path / "train" / "images"
    labels = tmp_path / "train" / "labels"
    images.mkdir(parents=True)
    labels.mkdir(parents=True)
    (images / "a.jpg").write_bytes(b"img-a")
    (labels / "a.txt").write_text("0 0.5 0.5 0.2 0.3\n", encoding="utf-8")
    return tmp_path


def test_interruptible_session_completes(tmp_path: Path) -> None:
    config = TrainConfig(
        dataset_dir=_minimal_dataset(tmp_path / "dataset"),
        runs_dir=tmp_path / "runs",
        epochs=3,
    )
    session = InterruptibleTrainSession(config, force_dry_run=True, epoch_sleep_s=0.01)
    events: list[TrainProgress] = []
    final = session.run(on_progress=events.append)
    assert final.finished and not final.cancelled
    assert final.result is not None
    assert final.result.mode == "dry_run"
    assert any(e.epoch == 3 for e in events)


def test_interruptible_session_can_cancel(tmp_path: Path) -> None:
    config = TrainConfig(
        dataset_dir=_minimal_dataset(tmp_path / "dataset"),
        runs_dir=tmp_path / "runs",
        epochs=50,
    )
    session = InterruptibleTrainSession(config, force_dry_run=True, epoch_sleep_s=0.2)

    def _run() -> TrainProgress:
        return session.run()

    import threading

    holder: list[TrainProgress] = []

    def _target() -> None:
        holder.append(_run())

    t = threading.Thread(target=_target)
    t.start()
    time.sleep(0.05)
    session.request_cancel()
    t.join(timeout=5.0)
    assert not t.is_alive()
    assert holder
    assert holder[0].cancelled
    assert holder[0].finished


def test_format_eta() -> None:
    assert format_eta(None) == "—"
    assert format_eta(12) == "12s"
    assert "m" in format_eta(90)


def test_mock_eval_metrics_recall_first() -> None:
    m = mock_eval_metrics(["a", "b", "c"])
    assert m.is_mock
    assert "Jetson" in m.note or "acceptance" in m.note
    assert m.missed_case_ids
    assert 0.0 <= m.recall <= 1.0
    d = m.to_dict()
    assert d["is_mock"] is True


def test_metrics_from_counts() -> None:
    m = metrics_from_counts(tp=8, fp=2, fn=2, missed_case_ids=["x"])
    assert m.recall == pytest.approx(0.8)
    assert m.precision == pytest.approx(0.8)
    assert m.missed_case_ids == ["x"]


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
    img.fill(QColor("#445566"))
    assert img.save(str(path), "PNG")


def test_eval_panel_recall_font_and_miss_jump(qapp, tmp_path: Path) -> None:
    from windows_studio.ingest import HardCase
    from windows_studio.review_ui import SampleFilter, build_review_queue, write_labels
    from windows_studio.review_ui.editor import save_review_manifest
    from windows_studio.review_ui.labels import YoloBox
    from windows_studio.shell import StudioMainWindow, WizardStepId
    from windows_studio.wizard import WizardConfig

    workspace = tmp_path / "ws"
    review_dir = workspace / "review"
    img = tmp_path / "miss1.png"
    _write_png(img)
    img2 = tmp_path / "ok1.png"
    _write_png(img2)
    cases = [
        HardCase("miss1", img, metadata={"reason": "missed_detection"}),
        HardCase("ok1", img2, metadata={"reason": "ok"}),
    ]
    items = build_review_queue(cases, review_dir)
    items[1].boxes = [YoloBox(0, 0.5, 0.5, 0.2, 0.2)]
    write_labels(items[1].label_path, items[1].boxes)
    items[1].suspect = False
    items[1].confirmed = True
    save_review_manifest(review_dir, items)

    config = WizardConfig(workspace=workspace, dry_run=True, epochs=2)
    win = StudioMainWindow(config)
    assert win.train_panel is not None
    assert win.eval_panel is not None

    win.set_step(WizardStepId.EVAL)
    assert not win.eval_panel.isHidden()
    assert win.review_tools.isHidden()
    assert win.train_panel.isHidden()

    # Recall label uses large font (≥ 28px via stylesheet).
    style = win.eval_panel.recall_label.styleSheet()
    assert "36px" in style
    assert "召回" in win.eval_panel.recall_label.text()

    # Inject metrics with known miss.
    win.eval_panel.set_metrics(
        EvalMetrics(
            recall=0.75,
            precision=0.9,
            missed_case_ids=["miss1"],
            is_mock=True,
            note="Studio mock — 不替代 Jetson acceptance",
        )
    )
    assert "75.0%" in win.eval_panel.recall_label.text()

    # Emit miss jump → review + case-id filter.
    win.eval_panel.jump_to_miss.emit("miss1")
    assert win.current_step() == WizardStepId.REVIEW
    visible = [i.case_id for i in win.sample_list.visible_items()]
    assert visible == ["miss1"]
    assert win.sample_list.case_id_override() == ["miss1"]

    # Clearing via set_filter restores combo mode.
    win.sample_list.set_filter(SampleFilter.ALL)
    assert win.sample_list.case_id_override() is None
    assert len(win.sample_list.visible_items()) == 2


def test_train_panel_widgets_and_cancel_api(qapp, tmp_path: Path) -> None:
    """Panel exposes start/stop; interruptibility covered by session unit test."""
    from windows_studio.train.panel import TrainPanel

    panel = TrainPanel(tmp_path / "ws", epochs=2, force_dry_run=True)
    assert panel._start_btn is not None
    assert panel._stop_btn is not None
    assert not panel._stop_btn.isEnabled()
    # Short complete run without leaving a dangling QThread.
    panel.set_epochs(1)
    finished: list = []
    panel.training_finished.connect(finished.append)
    panel.start_training()
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    panel.training_finished.connect(loop.quit)
    QTimer.singleShot(8000, loop.quit)
    loop.exec()
    panel._shutdown_worker(wait_ms=2000)
    assert finished
    assert finished[0].finished
    assert not finished[0].cancelled


def test_shell_train_step_shows_panel(qapp, tmp_path: Path) -> None:
    from windows_studio.shell import StudioMainWindow, WizardStepId
    from windows_studio.wizard import WizardConfig

    win = StudioMainWindow(WizardConfig(workspace=tmp_path / "ws", dry_run=True))
    win.set_step(WizardStepId.TRAIN)
    assert not win.train_panel.isHidden()
    assert win.eval_panel.isHidden()
    assert "训练" in win.tool_hint.text() or "epoch" in win.tool_hint.text().lower()
