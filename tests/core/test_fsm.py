"""Tests for core.fsm."""

import pytest

from core.fsm import IntrusionFSM


def test_enter_after_consecutive_frames():
    fsm = IntrusionFSM(enter_frames=2, exit_frames=3)
    assert fsm.update("slow") == 0
    assert fsm.update("slow") == 1


def test_stop_signal_overrides_slow():
    fsm = IntrusionFSM(enter_frames=1, exit_frames=5)
    assert fsm.update("slow") == 1
    assert fsm.update("stop") == 2


def test_exit_requires_consecutive_absence():
    fsm = IntrusionFSM(enter_frames=1, exit_frames=3)
    assert fsm.update("stop") == 2
    assert fsm.update(None) == 2
    assert fsm.update(None) == 2
    assert fsm.update(None) == -1


def test_fault_returns_minus_one():
    fsm = IntrusionFSM(enter_frames=1, exit_frames=1)
    fsm.set_fault(True)
    assert fsm.update("stop") == -1


def test_brief_dropout_does_not_deactivate():
    fsm = IntrusionFSM(enter_frames=2, exit_frames=5)
    for _ in range(2):
        fsm.update("slow")
    assert fsm.update("slow") == 1
    assert fsm.update(None) == 1  # exit_streak=1, still active
    assert fsm.update("slow") == 1
