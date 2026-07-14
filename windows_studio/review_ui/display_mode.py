"""Canvas display modes — raw / labels / labels+pred (#53)."""

from __future__ import annotations

from enum import Enum


class DisplayMode(str, Enum):
    RAW = "raw"
    LABELS = "labels"
    LABELS_PLUS_PRED = "labels_plus_pred"


DISPLAY_MODE_LABELS: dict[DisplayMode, str] = {
    DisplayMode.RAW: "原图",
    DisplayMode.LABELS: "标注",
    DisplayMode.LABELS_PLUS_PRED: "标注+预测",
}

_CYCLE: tuple[DisplayMode, ...] = (
    DisplayMode.RAW,
    DisplayMode.LABELS,
    DisplayMode.LABELS_PLUS_PRED,
)


def next_display_mode(current: DisplayMode) -> DisplayMode:
    idx = _CYCLE.index(current)
    return _CYCLE[(idx + 1) % len(_CYCLE)]


def display_mode_caption(mode: DisplayMode) -> str:
    return DISPLAY_MODE_LABELS[mode]
