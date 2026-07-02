"""Tests for core.tracking (detection hold)."""

from core.postprocess import Detection
from core.tracking import DetectionHold


def test_hold_reuses_last_within_window():
    hold = DetectionHold(hold_ms=500)
    d1 = [Detection(0, 0, 50, 100, 0.9)]
    assert hold.apply(d1, 1000.0) == d1
    assert hold.apply([], 1200.0) == d1
    assert hold.apply([], 1400.0) == d1


def test_hold_expires_after_window():
    hold = DetectionHold(hold_ms=300)
    d1 = [Detection(0, 0, 50, 100, 0.9)]
    hold.apply(d1, 1000.0)
    assert hold.apply([], 1600.0) == []


def test_hold_reset():
    hold = DetectionHold(hold_ms=500)
    hold.apply([Detection(0, 0, 10, 10, 0.8)], 0.0)
    hold.reset()
    assert hold.apply([], 100.0) == []
