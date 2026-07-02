"""Optional TensorRT integration test (skipped when engine or CUDA unavailable)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

ENGINE = Path("models/stock/yolov8s.engine")


def _trt_available() -> bool:
    try:
        import tensorrt  # noqa: F401
        import torch

        return torch.cuda.is_available() and ENGINE.is_file()
    except ImportError:
        return False


@pytest.mark.skipif(not _trt_available(), reason="TensorRT engine or CUDA not available")
def test_trt_backend_infer_raw():
    from core.postprocess import postprocess_yolo
    from detect.backend import create_backend

    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    with create_backend("tensorrt", ENGINE) as backend:
        backend.warmup(1)
        raw = backend.infer_raw(frame)

    assert raw.ndim >= 2
    dets = postprocess_yolo(raw, conf=0.25, nms_iou=0.45, min_area=0.0, class_ids=(0,))
    assert isinstance(dets, list)
