"""Multi-station runtime: shared camera infer once, independent station signals (#34)."""

from __future__ import annotations

import numpy as np
import pytest

from app.multi_runtime import MultiStationRuntime, group_stations_by_camera
from app.pipeline import StationRunner
from core.config import AppConfig, CameraConfig, ParamGroup, StationConfig
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


class CountingBackend(InferBackend):
    input_size = DEFAULT_INPUT_SIZE

    def __init__(self, output: np.ndarray) -> None:
        self._output = output
        self.infer_calls = 0

    def load(self, model_path: str) -> None:
        return None

    def infer_batch(self, batch: np.ndarray) -> np.ndarray:
        self.infer_calls += 1
        return self._output

    def warmup(self, n: int = 3) -> None:
        return None

    def close(self) -> None:
        return None


def _param(
    *,
    id: str,
    slow: list[list[float]],
    stop: list[list[float]],
    enter_frames: int = 2,
) -> ParamGroup:
    return ParamGroup(
        id=id,
        ref_width=640,
        ref_height=480,
        slow_polygon=slow,
        stop_polygon=stop,
        conf=0.25,
        enter_frames=enter_frames,
        exit_frames=3,
        hold_ms=0,
        min_overlap=0.05,
        nms_iou=0.45,
        min_box_area=0.0,
    )


@pytest.fixture
def two_station_shared_camera_config() -> AppConfig:
    """Two stations, same camera; station_a STOP zone covers person, station_b does not."""
    # Person center ~ (320, 300) in 640x480 letterbox-aligned coords (see test_pipeline).
    stop_cover = [[200, 100], [440, 100], [440, 380], [200, 380]]
    slow_cover = [[50, 50], [590, 50], [590, 430], [50, 430]]
    # Far corner: no overlap with person box.
    empty_zone = [[10, 10], [40, 10], [40, 40], [10, 40]]

    return AppConfig(
        cameras=[
            CameraConfig(id="cam0", source_type="video_file", path="unused.mp4", label="shared"),
        ],
        param_groups=[
            _param(id="pg_stop", slow=slow_cover, stop=stop_cover),
            _param(id="pg_empty", slow=empty_zone, stop=empty_zone),
        ],
        stations=[
            StationConfig(
                id="station_a",
                camera_id="cam0",
                param_group_id="pg_stop",
                detect_mode="person",
                enabled=True,
            ),
            StationConfig(
                id="station_b",
                camera_id="cam0",
                param_group_id="pg_empty",
                detect_mode="person",
                enabled=True,
            ),
        ],
    )


def test_group_stations_by_camera(two_station_shared_camera_config: AppConfig) -> None:
    groups = group_stations_by_camera(two_station_shared_camera_config)
    assert list(groups.keys()) == ["cam0"]
    assert [s.id for s in groups["cam0"]] == ["station_a", "station_b"]


def test_shared_camera_infer_once_independent_signals(
    two_station_shared_camera_config: AppConfig,
) -> None:
    runtime = MultiStationRuntime(two_station_shared_camera_config)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    raw = _make_yolo_output(320, 300, 80, 160, 0.95)
    backend = CountingBackend(raw)

    # Frame 0: enter debounce → transitional 0 for stop station; empty stays -1
    r0 = runtime.process_camera_frame(
        "cam0",
        frame,
        backend=backend,
        frame_index=0,
        timestamp_ms=0.0,
    )
    assert backend.infer_calls == 1
    assert len(r0) == 2
    by_id = {r.station_id: r for r in r0}
    assert by_id["station_a"].signal == 0
    assert by_id["station_a"].zone_hit == "stop"
    assert by_id["station_b"].signal == -1
    assert by_id["station_b"].zone_hit is None

    # Frame 1: station_a confirms STOP (2); station_b still safe
    r1 = runtime.process_camera_frame(
        "cam0",
        frame,
        backend=backend,
        frame_index=1,
        timestamp_ms=66.0,
    )
    assert backend.infer_calls == 2  # one infer per frame, not per station
    by_id = {r.station_id: r for r in r1}
    assert by_id["station_a"].signal == 2
    assert by_id["station_b"].signal == -1


def test_naive_two_runners_would_double_infer(
    two_station_shared_camera_config: AppConfig,
) -> None:
    """Contrast: calling StationRunner.process twice hits backend twice."""
    cfg = two_station_shared_camera_config
    runners = [
        StationRunner(station=st, param=next(p for p in cfg.param_groups if p.id == st.param_group_id))
        for st in cfg.stations
        if st.enabled
    ]
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    backend = CountingBackend(_make_yolo_output(320, 300, 80, 160, 0.95))
    for runner in runners:
        runner.process(frame, backend=backend, frame_index=0, timestamp_ms=0.0)
    assert backend.infer_calls == 2


def test_process_unknown_camera_raises(two_station_shared_camera_config: AppConfig) -> None:
    runtime = MultiStationRuntime(two_station_shared_camera_config)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    backend = CountingBackend(_make_yolo_output(320, 300, 80, 160, 0.95))
    with pytest.raises(ValueError, match="no enabled station"):
        runtime.process_camera_frame(
            "cam_missing",
            frame,
            backend=backend,
            frame_index=0,
            timestamp_ms=0.0,
        )
