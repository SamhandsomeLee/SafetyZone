"""Safety zone geometry: polygon scaling, anchor hit, overlap ratio."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Sequence

import numpy as np

AnchorMode = Literal["person", "object"]
ZoneHit = Literal["stop", "slow"] | None

Box = tuple[float, float, float, float]  # x1, y1, x2, y2
Point = tuple[float, float]
Polygon = Sequence[Point]


class _Anchor(str, Enum):
    PERSON = "person"
    OBJECT = "object"


def scale_polygon(
    polygon: Polygon,
    ref_size: tuple[int, int],
    frame_size: tuple[int, int],
) -> np.ndarray:
    """Scale polygon from reference resolution to current frame size."""
    ref_w, ref_h = ref_size
    frame_w, frame_h = frame_size
    if ref_w <= 0 or ref_h <= 0:
        raise ValueError("ref_size must be positive")

    sx = frame_w / ref_w
    sy = frame_h / ref_h
    pts = np.asarray(polygon, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError("polygon must be Nx2")
    scaled = pts.copy()
    scaled[:, 0] *= sx
    scaled[:, 1] *= sy
    return scaled


def box_anchor(box: Box, mode: AnchorMode) -> Point:
    """Person: bottom-center (cx, y2). Object: center (cx, cy)."""
    x1, y1, x2, y2 = box
    cx = (x1 + x2) / 2.0
    if mode == "person":
        return (cx, y2)
    return (cx, (y1 + y2) / 2.0)


def point_in_polygon(point: Point, polygon: np.ndarray) -> bool:
    """Ray-casting point-in-polygon test."""
    if polygon.shape[0] < 3:
        return False
    x, y = point
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _polygon_bbox(polygon: np.ndarray) -> tuple[float, float, float, float]:
    xs = polygon[:, 0]
    ys = polygon[:, 1]
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


def box_polygon_overlap_ratio(box: Box, polygon: np.ndarray) -> float:
    """
    Approximate overlap area(box, polygon) / area(box).
    Uses pixel grid inside bbox intersection for robustness without cv2.
    """
    x1, y1, x2, y2 = box
    box_area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if box_area <= 0 or polygon.shape[0] < 3:
        return 0.0

    px1, py1, px2, py2 = _polygon_bbox(polygon)
    ix1, iy1 = max(x1, px1), max(y1, py1)
    ix2, iy2 = min(x2, px2), min(y2, py2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    # Sample grid (cap resolution for speed)
    gw = min(64, max(4, int(ix2 - ix1)))
    gh = min(64, max(4, int(iy2 - iy1)))
    xs = np.linspace(ix1, ix2, gw, endpoint=False) + (ix2 - ix1) / (2 * gw)
    ys = np.linspace(iy1, iy2, gh, endpoint=False) + (iy2 - iy1) / (2 * gh)

    hits = 0
    total = gw * gh
    for py in ys:
        for px in xs:
            if point_in_polygon((float(px), float(py)), polygon):
                hits += 1
    return hits / total if total else 0.0


def _hit_zone(
    box: Box,
    polygon: np.ndarray,
    anchor: Point,
    min_overlap: float,
) -> bool:
    if point_in_polygon(anchor, polygon):
        return True
    return box_polygon_overlap_ratio(box, polygon) >= min_overlap


def judge_zone(
    box: Box,
    *,
    slow_polygon: Polygon,
    stop_polygon: Polygon,
    ref_size: tuple[int, int],
    frame_size: tuple[int, int],
    anchor_mode: AnchorMode = "person",
    min_overlap: float = 0.1,
) -> ZoneHit:
    """
    Judge which zone a detection box hits.
    Priority: inner STOP > outer SLOW > none.
    """
    if min_overlap < 0 or min_overlap > 1:
        raise ValueError("min_overlap must be in [0, 1]")

    slow = scale_polygon(slow_polygon, ref_size, frame_size)
    stop = scale_polygon(stop_polygon, ref_size, frame_size)
    anchor = box_anchor(box, anchor_mode)

    if _hit_zone(box, stop, anchor, min_overlap):
        return "stop"
    if _hit_zone(box, slow, anchor, min_overlap):
        return "slow"
    return None
