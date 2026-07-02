"""Tests for core.postprocess."""

import numpy as np
import pytest

from core.postprocess import Detection, filter_detections, nms, parse_yolo_output, postprocess_yolo


def _make_yolo_output(candidates: list[tuple[float, float, float, float, float, int]]) -> np.ndarray:
    """
    Build (1, 4+nc, N) YOLOv8 output.
    Each candidate: cx, cy, w, h, score, class_id (nc=80).
    """
    nc = 80
    n = len(candidates)
    out = np.zeros((1, 4 + nc, n), dtype=np.float32)
    for i, (cx, cy, w, h, score, cls) in enumerate(candidates):
        out[0, 0, i] = cx
        out[0, 1, i] = cy
        out[0, 2, i] = w
        out[0, 3, i] = h
        out[0, 4 + cls, i] = score
    return out


def test_parse_yolo_output_person_only():
    # Two boxes: person @0 with high score, person @0 low, class 2 (car) high
    raw = _make_yolo_output(
        [
            (100, 100, 40, 80, 0.9, 0),
            (200, 200, 30, 60, 0.2, 0),
            (150, 150, 50, 50, 0.95, 2),
        ]
    )
    dets = parse_yolo_output(raw, conf=0.5, class_ids=(0,))
    assert len(dets) == 1
    assert dets[0].class_id == 0
    assert dets[0].conf == pytest.approx(0.9)


def test_nms_suppresses_overlap():
    a = Detection(0, 0, 100, 100, 0.9, 0)
    b = Detection(10, 10, 110, 110, 0.8, 0)
    c = Detection(300, 300, 400, 400, 0.85, 0)
    kept = nms([a, b, c], iou_threshold=0.3)
    assert len(kept) == 2
    assert kept[0].conf == 0.9


def test_filter_detections_min_area():
    small = Detection(0, 0, 10, 10, 0.9, 0)
    large = Detection(0, 0, 30, 30, 0.9, 0)
    out = filter_detections([small, large], conf=0.5, min_area=400)
    assert len(out) == 1
    assert out[0].area == large.area


def test_postprocess_yolo_pipeline():
    raw = _make_yolo_output(
        [
            (50, 50, 40, 40, 0.88, 0),
            (52, 52, 40, 40, 0.75, 0),
            (300, 300, 60, 120, 0.82, 0),
        ]
    )
    dets = postprocess_yolo(raw, conf=0.5, nms_iou=0.45, min_area=100)
    assert len(dets) == 2


def test_parse_transposed_layout():
    raw = _make_yolo_output([(100, 100, 20, 40, 0.7, 0)])[0].T[np.newaxis, ...]
    dets = parse_yolo_output(raw, conf=0.5, class_ids=(0,))
    assert len(dets) == 1
