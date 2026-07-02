"""Platform-independent core logic (no cv2 / TensorRT / snap7)."""

from core.fsm import IntrusionFSM
from core.zone import AnchorMode, ZoneHit, judge_zone, scale_polygon

__all__ = [
    "AnchorMode",
    "IntrusionFSM",
    "ZoneHit",
    "judge_zone",
    "scale_polygon",
]
