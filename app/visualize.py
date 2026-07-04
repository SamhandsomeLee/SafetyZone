"""Render BGR overlay frames for the monitor UI."""

from __future__ import annotations

import numpy as np

from app.signal_display import SIGNAL_LABELS
from core.postprocess import Detection
from core.zone import judge_zone, scale_polygon


def _zone_color_bgr(zone: str | None) -> tuple[int, int, int]:
    if zone == "stop":
        return (0, 0, 255)
    if zone == "slow":
        return (0, 200, 255)
    return (0, 255, 0)


def draw_zones(
    frame: np.ndarray,
    *,
    slow_polygon: list[list[float]],
    stop_polygon: list[list[float]],
    ref_size: tuple[int, int],
) -> None:
    import cv2

    frame_h, frame_w = frame.shape[:2]
    frame_size = (frame_w, frame_h)
    slow = scale_polygon(slow_polygon, ref_size, frame_size).astype(np.int32)
    stop = scale_polygon(stop_polygon, ref_size, frame_size).astype(np.int32)

    overlay = frame.copy()
    cv2.fillPoly(overlay, [slow], (0, 180, 255))
    cv2.fillPoly(overlay, [stop], (0, 0, 255))
    cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)
    cv2.polylines(frame, [slow], True, (0, 200, 255), 2)
    cv2.polylines(frame, [stop], True, (0, 0, 255), 2)


def draw_detections_with_zones(
    frame: np.ndarray,
    detections: list[Detection],
    *,
    slow_polygon: list[list[float]],
    stop_polygon: list[list[float]],
    ref_size: tuple[int, int],
    anchor_mode: str,
    min_overlap: float,
) -> None:
    import cv2

    frame_h, frame_w = frame.shape[:2]
    for det in detections:
        zone = judge_zone(
            det.as_box(),
            slow_polygon=slow_polygon,
            stop_polygon=stop_polygon,
            ref_size=ref_size,
            frame_size=(frame_w, frame_h),
            anchor_mode=anchor_mode,  # type: ignore[arg-type]
            min_overlap=min_overlap,
        )
        color = _zone_color_bgr(zone)
        x1, y1, x2, y2 = map(int, (det.x1, det.y1, det.x2, det.y2))
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"person {det.conf:.2f}"
        if zone:
            label += f" [{zone.upper()}]"
        (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
        ty = max(th + 6, y1 - 4)
        cv2.rectangle(frame, (x1, ty - th - 6), (x1 + tw + 4, ty + baseline), color, -1)
        cv2.putText(frame, label, (x1 + 2, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)


def draw_hud(
    frame: np.ndarray,
    *,
    signal: int,
    frame_index: int,
    infer_ms: float,
    det_count: int,
    process_fps: float,
    fault: bool,
) -> None:
    import cv2

    if fault:
        label, color = "FAULT", (0, 0, 255)
    else:
        label, _hex = SIGNAL_LABELS.get(signal, (str(signal), "#ffffff"))
        color = {
            "SAFE": (80, 200, 80),
            "WARN": (0, 200, 255),
            "SLOW": (0, 180, 255),
            "STOP": (0, 0, 255),
        }.get(label, (255, 255, 255))

    cv2.rectangle(frame, (0, 0), (frame.shape[1], 36), (20, 20, 20), -1)
    cv2.putText(
        frame,
        f"signal={signal}({label})  f={frame_index}  dets={det_count}  "
        f"{infer_ms:.0f}ms  {process_fps:.1f}fps",
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        color,
        2,
    )


def render_monitor_frame(
    frame: np.ndarray,
    *,
    detections: list[Detection],
    slow_polygon: list[list[float]],
    stop_polygon: list[list[float]],
    ref_size: tuple[int, int],
    anchor_mode: str,
    min_overlap: float,
    signal: int,
    frame_index: int,
    infer_ms: float,
    process_fps: float,
    fault: bool,
    draw_boxes: bool = True,
) -> np.ndarray:
    vis = frame.copy()
    draw_zones(
        vis,
        slow_polygon=slow_polygon,
        stop_polygon=stop_polygon,
        ref_size=ref_size,
    )
    if draw_boxes and detections:
        draw_detections_with_zones(
            vis,
            detections,
            slow_polygon=slow_polygon,
            stop_polygon=stop_polygon,
            ref_size=ref_size,
            anchor_mode=anchor_mode,
            min_overlap=min_overlap,
        )
    draw_hud(
        vis,
        signal=signal,
        frame_index=frame_index,
        infer_ms=infer_ms,
        det_count=len(detections),
        process_fps=process_fps,
        fault=fault,
    )
    return vis
