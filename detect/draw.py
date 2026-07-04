"""Draw YOLO person detections on BGR frames."""

from __future__ import annotations

import numpy as np

from core.postprocess import Detection


def draw_person_boxes(
    frame: np.ndarray,
    detections: list[Detection],
    *,
    color: tuple[int, int, int] = (0, 255, 0),
    thickness: int = 2,
    show_conf: bool = True,
    label_prefix: str = "person",
) -> None:
    """Draw axis-aligned boxes and optional confidence labels in-place."""
    import cv2

    for det in detections:
        x1, y1, x2, y2 = map(int, (det.x1, det.y1, det.x2, det.y2))
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
        if show_conf:
            label = f"{label_prefix} {det.conf:.2f}"
            (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            ty = max(th + 6, y1 - 4)
            cv2.rectangle(frame, (x1, ty - th - 6), (x1 + tw + 4, ty + baseline), color, -1)
            cv2.putText(
                frame,
                label,
                (x1 + 2, ty),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 0, 0),
                2,
            )
