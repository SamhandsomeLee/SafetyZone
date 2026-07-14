"""Tests for windows_studio three-pane shell (#52 + #53)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from windows_studio.shell import STEP_DEFS, StudioMainWindow, WizardStepId
from windows_studio.wizard import WizardConfig


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_shell_has_three_panes_and_step_bar(qapp: QApplication, tmp_path: Path) -> None:
    config = WizardConfig(workspace=tmp_path / "ws", dry_run=True)
    win = StudioMainWindow(config)
    assert win.step_bar is not None
    assert win.case_list is not None
    assert win.sample_list is not None
    assert win.canvas is not None
    assert win.canvas_hint is not None
    assert win.tool_hint is not None
    assert len(STEP_DEFS) == 5
    assert win.current_step() == WizardStepId.INGEST
    # Empty workspace → friendly empty canvas state
    assert win.canvas.display_mode is not None
    assert len(win.sample_list.items()) == 0


def test_step_bar_click_switches_hint(qapp: QApplication, tmp_path: Path) -> None:
    config = WizardConfig(workspace=tmp_path / "ws", dry_run=True)
    win = StudioMainWindow(config)
    win.set_step(WizardStepId.REVIEW)
    assert win.current_step() == WizardStepId.REVIEW
    assert not win.review_tools.isHidden()
    assert "勿漏标" in win.tool_hint.text() or "复核" in win.tool_hint.text()
    win.set_step(WizardStepId.TRAIN)
    assert win.current_step() == WizardStepId.TRAIN
    assert win.review_tools.isHidden()
    assert not win.train_panel.isHidden()
    assert "训练" in win.tool_hint.text() or "epoch" in win.tool_hint.text().lower()
    win.set_step(WizardStepId.EVAL)
    assert not win.eval_panel.isHidden()
    assert win.train_panel.isHidden()
    assert "召回" in win.tool_hint.text() or "acceptance" in win.tool_hint.text()


def test_cli_info_still_works() -> None:
    from windows_studio.app import main

    assert main([]) == 0
