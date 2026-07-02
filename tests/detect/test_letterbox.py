"""Tests for detect.letterbox (no TensorRT required)."""

import numpy as np

from detect.letterbox import letterbox, preprocess_bgr, scale_boxes_xyxy


def test_letterbox_output_shape():
    image = np.zeros((480, 640, 3), dtype=np.uint8)
    boxed, meta = letterbox(image, new_shape=640)
    assert boxed.shape == (640, 640, 3)
    assert meta.orig_width == 640
    assert meta.orig_height == 480
    assert meta.ratio > 0


def test_preprocess_bgr_nchw():
    image = np.full((720, 1280, 3), 127, dtype=np.uint8)
    batch, meta = preprocess_bgr(image, input_size=640)
    assert batch.shape == (1, 3, 640, 640)
    assert batch.dtype == np.float32
    assert 0.0 <= batch.max() <= 1.0
    assert meta.orig_width == 1280


def test_scale_boxes_xyxy_roundtrip_padding():
    image = np.zeros((1000, 800, 3), dtype=np.uint8)
    _boxed, meta = letterbox(image, new_shape=640)

    boxes = np.array([[280.0, 280.0, 360.0, 360.0]], dtype=np.float64)
    scaled = scale_boxes_xyxy(boxes, meta)
    cx = (scaled[0, 0] + scaled[0, 2]) / 2.0
    cy = (scaled[0, 1] + scaled[0, 3]) / 2.0
    assert 350 <= cx <= 450
    assert 450 <= cy <= 550
