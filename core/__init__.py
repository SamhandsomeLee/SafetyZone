"""Platform-independent core logic (no cv2 / TensorRT / snap7)."""

from core.config import AppConfig, ConfigError, load_config, save_config
from core.fsm import IntrusionFSM
from core.postprocess import Detection, postprocess_yolo
from core.tracking import DetectionHold
from core.zone import AnchorMode, ZoneHit, judge_zone, scale_polygon

__all__ = [
    "AnchorMode",
    "AppConfig",
    "ConfigError",
    "Detection",
    "DetectionHold",
    "IntrusionFSM",
    "ZoneHit",
    "judge_zone",
    "load_config",
    "postprocess_yolo",
    "save_config",
    "scale_polygon",
]
