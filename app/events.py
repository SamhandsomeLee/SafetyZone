"""Pipeline event types (frame / detection / signal)."""

from __future__ import annotations

from dataclasses import dataclass

from core.postprocess import Detection


@dataclass(frozen=True)
class FrameResult:
    """Per-frame output for one station."""

    station_id: str
    frame_index: int
    timestamp_ms: float
    signal: int
    zone_hit: str | None
    detections: tuple[Detection, ...]
    fault: bool = False


@dataclass(frozen=True)
class PipelineSummary:
    """Aggregated run statistics."""

    frames: int
    signals: tuple[int, ...]
    signal_changes: int
