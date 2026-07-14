"""Tests for windows_studio three-pane shell (#52)."""

from __future__ import annotations

from pathlib import Path

import pytest

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
    assert win.canvas_hint is not None
    assert win.tool_hint is not None
    assert len(STEP_DEFS) == 5
    assert win.current_step() == WizardStepId.INGEST


def test_step_bar_click_switches_hint(qapp: QApplication, tmp_path: Path) -> None:
    config = WizardConfig(workspace=tmp_path / "ws", dry_run=True)
    win = StudioMainWindow(config)
    win.set_step(WizardStepId.REVIEW)
    assert win.current_step() == WizardStepId.REVIEW
    assert "勿漏标" in win.canvas_hint.text() or "复核" in win.canvas_hint.text()
    win.set_step(WizardStepId.TRAIN)
    assert win.current_step() == WizardStepId.TRAIN
    assert "训练" in win.tool_hint.text() or "#54" in win.tool_hint.text()


def test_cli_info_still_works() -> None:
    from windows_studio.app import main

    assert main([]) == 0
