"""Pipeline tests with mock inference backend (no TensorRT)."""

from __future__ import annotations

import numpy as np
import pytest

from app.pipeline import StationRunner, _best_zone_hit
from core.config import ParamGroup, StationConfig
from core.fsm import IntrusionFSM
from core.postprocess import Detection
from detect.backend import InferBackend
from detect.letterbox import DEFAULT_INPUT_SIZE


def _make_yolo_output(cx: float, cy: float, w: float, h: float, score: float) -> np.ndarray:
    nc = 80
    out = np.zeros((1, 4 + nc, 1), dtype=np.float32)
    out[0, 0, 0] = cx
    out[0, 1, 0] = cy
    out[0, 2, 0] = w
    out[0, 3, 0] = h
    out[0, 4, 0] = score
    return out


class MockBackend(InferBackend):
    input_size = DEFAULT_INPUT_SIZE

    def __init__(self, output: np.ndarray) -> None:
        self._output = output

    def load(self, model_path: str) -> None:
        return None

    def infer_batch(self, batch: np.ndarray) -> np.ndarray:
        return self._output

    def warmup(self, n: int = 3) -> None:
        return None

    def close(self) -> None:
        return None


@pytest.fixture
def param_group() -> ParamGroup:
    return ParamGroup(
        id="default",
        ref_width=640,
        ref_height=480,
        slow_polygon=[[50, 50], [590, 50], [590, 430], [50, 430]],
        stop_polygon=[[200, 100], [440, 100], [440, 380], [200, 380]],
        conf=0.25,
        enter_frames=2,
        exit_frames=3,
        hold_ms=0,
        min_overlap=0.05,
        nms_iou=0.45,
        min_box_area=0.0,
    )


@pytest.fixture
def station() -> StationConfig:
    return StationConfig(
        id="station0",
        camera_id="cam0",
        param_group_id="default",
        detect_mode="person",
        enabled=True,
    )


def test_best_zone_hit_stop_priority(param_group: ParamGroup):
    dets = [Detection(x1=210, y1=120, x2=260, y2=370, conf=0.9, class_id=0)]
    assert _best_zone_hit(dets, param=param_group, frame_size=(640, 480), anchor_mode="person") == "stop"


def test_station_runner_signal_sequence(param_group: ParamGroup, station: StationConfig):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    runner = StationRunner(station=station, param=param_group)

    # Person center in stop zone (640x480 frame, box maps via letterbox scaling)
    raw = _make_yolo_output(320, 300, 80, 160, 0.95)
    backend = MockBackend(raw)

    assert runner.process(frame, backend=backend, frame_index=0, timestamp_ms=0)[0] == 0
    signal = runner.process(frame, backend=backend, frame_index=1, timestamp_ms=66)[0]
    assert signal == 2


def test_fsm_alignment_without_inference():
    fsm = IntrusionFSM(enter_frames=2, exit_frames=3)
    assert fsm.update("slow") == 0
    assert fsm.update("slow") == 1
    assert fsm.update(None) == 1
    assert fsm.update(None) == 1
    assert fsm.update(None) == -1
