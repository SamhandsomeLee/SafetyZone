"""YOLO detection post-processing: parse, NMS, person-only filter."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PERSON_CLASS_ID = 0


@dataclass(frozen=True)
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    conf: float
    class_id: int = PERSON_CLASS_ID

    @property
    def area(self) -> float:
        return max(0.0, self.x2 - self.x1) * max(0.0, self.y2 - self.y1)

    def as_box(self) -> tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)


def xywh_to_xyxy(cx: float, cy: float, w: float, h: float) -> tuple[float, float, float, float]:
    half_w, half_h = w / 2.0, h / 2.0
    return (cx - half_w, cy - half_h, cx + half_w, cy + half_h)


def _normalize_yolo_layout(arr: np.ndarray) -> np.ndarray:
    """
    Ensure shape (N, 4+nc).

    YOLOv8 ONNX uses (4+nc, N); transposed or batched layouts also appear in tests.
    """
    rows, cols = arr.shape
    if rows >= 5 and cols >= 5:
        if rows <= 512 and cols > rows:
            return arr.T
        return arr
    if rows >= 5 and rows <= 512 and cols < rows:
        return arr.T
    if cols >= 5 and cols <= 512 and rows < cols:
        return arr
    raise ValueError(f"cannot infer YOLO layout from shape {arr.shape}")


def _box_iou(a: Detection, b: Detection) -> float:
    ix1 = max(a.x1, b.x1)
    iy1 = max(a.y1, b.y1)
    ix2 = min(a.x2, b.x2)
    iy2 = min(a.y2, b.y2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    union = a.area + b.area - inter
    return inter / union if union > 0 else 0.0


def nms(detections: list[Detection], iou_threshold: float) -> list[Detection]:
    """Greedy NMS sorted by confidence descending."""
    if iou_threshold <= 0 or not detections:
        return list(detections)

    remaining = sorted(detections, key=lambda d: d.conf, reverse=True)
    kept: list[Detection] = []

    while remaining:
        best = remaining.pop(0)
        kept.append(best)
        remaining = [d for d in remaining if _box_iou(best, d) < iou_threshold]

    return kept


def filter_detections(
    detections: list[Detection],
    *,
    conf: float,
    min_area: float,
    class_ids: tuple[int, ...] = (PERSON_CLASS_ID,),
) -> list[Detection]:
    allowed = set(class_ids)
    out: list[Detection] = []
    for det in detections:
        if det.class_id not in allowed:
            continue
        if det.conf < conf:
            continue
        if det.area < min_area:
            continue
        out.append(det)
    return out


def _parse_person_vectorized(
    arr: np.ndarray,
    *,
    conf: float,
    min_area: float,
) -> list[Detection]:
    """Fast path for COCO class-0 (person) only."""
    scores = arr[:, 4]
    mask = scores >= conf
    if not np.any(mask):
        return []

    boxes = arr[mask, :4]
    scores = scores[mask]
    cx = boxes[:, 0]
    cy = boxes[:, 1]
    w = boxes[:, 2]
    h = boxes[:, 3]
    half_w = w * 0.5
    half_h = h * 0.5
    x1 = cx - half_w
    y1 = cy - half_h
    x2 = cx + half_w
    y2 = cy + half_h
    areas = w * h
    if min_area > 0:
        area_mask = areas >= min_area
        if not np.any(area_mask):
            return []
        x1, y1, x2, y2, scores = x1[area_mask], y1[area_mask], x2[area_mask], y2[area_mask], scores[area_mask]

    return [
        Detection(
            x1=float(x1[i]),
            y1=float(y1[i]),
            x2=float(x2[i]),
            y2=float(y2[i]),
            conf=float(scores[i]),
            class_id=PERSON_CLASS_ID,
        )
        for i in range(scores.shape[0])
    ]


def parse_yolo_output(
    output: np.ndarray,
    *,
    conf: float = 0.25,
    min_area: float = 0.0,
    class_ids: tuple[int, ...] = (PERSON_CLASS_ID,),
) -> list[Detection]:
    """
    Parse YOLOv8-style ONNX output to detections (before NMS).

    Supports shapes:
      - (1, 4+nc, N)  — standard YOLOv8 export
      - (1, N, 4+nc)
      - (N, 4+nc)
    Box format: center-x, center-y, width, height (letterbox space).
    """
    arr = np.asarray(output, dtype=np.float32)
    if arr.ndim == 3:
        arr = arr[0]

    if arr.ndim != 2:
        raise ValueError(f"expected 2D predictions after batch squeeze, got shape {arr.shape}")

    arr = _normalize_yolo_layout(arr)

    if arr.shape[1] < 5:
        raise ValueError(f"expected at least 5 columns (box + class), got {arr.shape[1]}")

    if class_ids == (PERSON_CLASS_ID,):
        return _parse_person_vectorized(arr, conf=conf, min_area=min_area)

    boxes = arr[:, :4]
    class_scores = arr[:, 4:]

    detections: list[Detection] = []
    for i in range(arr.shape[0]):
        scores = class_scores[i]
        if scores.size == 1:
            class_id = int(class_ids[0]) if class_ids else 0
            score = float(scores[0])
        else:
            class_id = int(np.argmax(scores))
            score = float(scores[class_id])

        if score < conf:
            continue
        if class_ids and class_id not in class_ids:
            continue

        cx, cy, w, h = boxes[i]
        x1, y1, x2, y2 = xywh_to_xyxy(float(cx), float(cy), float(w), float(h))
        det = Detection(x1=x1, y1=y1, x2=x2, y2=y2, conf=score, class_id=class_id)
        if det.area < min_area:
            continue
        detections.append(det)

    return detections


def postprocess_yolo(
    output: np.ndarray,
    *,
    conf: float,
    nms_iou: float,
    min_area: float,
    class_ids: tuple[int, ...] = (PERSON_CLASS_ID,),
) -> list[Detection]:
    """Parse → filter → NMS pipeline for person detection."""
    dets = parse_yolo_output(output, conf=conf, min_area=min_area, class_ids=class_ids)
    return nms(dets, nms_iou)
