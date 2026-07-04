"""Frame payload types for UI bridge (worker thread → Qt main thread)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.postprocess import Detection


@dataclass(frozen=True)
class FramePayload:
    """One annotated frame for the monitor view."""

    station_id: str
    frame_index: int
    signal: int
    zone_hit: str | None
    detections: tuple[Detection, ...]
    infer_ms: float
    process_fps: float
    fault: bool
    overlay_bgr: np.ndarray
