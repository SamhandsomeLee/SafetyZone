"""Simple detection hold across missed frames (HoldMs, v1 without multi-object tracking)."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.postprocess import Detection


@dataclass
class DetectionHold:
    """
    When current frame has no detections, reuse the last non-empty result
    for up to hold_ms milliseconds (recall-oriented miss tolerance).
    """

    hold_ms: float
    _last: list[Detection] = field(default_factory=list)
    _last_ts_ms: float | None = None

    def apply(self, detections: list[Detection], timestamp_ms: float) -> list[Detection]:
        if detections:
            self._last = list(detections)
            self._last_ts_ms = timestamp_ms
            return detections

        if self._last and self._last_ts_ms is not None:
            if timestamp_ms - self._last_ts_ms <= self.hold_ms:
                return list(self._last)

        return []

    def reset(self) -> None:
        self._last = []
        self._last_ts_ms = None
