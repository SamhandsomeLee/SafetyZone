"""Detection pipeline: infer → postprocess → zone → FSM → signal."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from core.config import AppConfig, ParamGroup, StationConfig, load_config
from core.fsm import IntrusionFSM
from core.postprocess import Detection, postprocess_yolo
from core.tracking import DetectionHold
from core.zone import ZoneHit, judge_zone
from detect.backend import InferBackend
from detect.letterbox import LetterboxMeta, preprocess_bgr, scale_boxes_xyxy


def _scale_detection(det: Detection, meta: LetterboxMeta) -> Detection:
    arr = scale_boxes_xyxy(
        np.array([[det.x1, det.y1, det.x2, det.y2]], dtype=np.float64),
        meta,
    )[0]
    return Detection(
        x1=float(arr[0]),
        y1=float(arr[1]),
        x2=float(arr[2]),
        y2=float(arr[3]),
        conf=det.conf,
        class_id=det.class_id,
    )


def scale_detections_to_frame(
    detections: list[Detection],
    meta: LetterboxMeta,
) -> list[Detection]:
    """Map letterbox-space detections to original frame coordinates."""
    return [_scale_detection(det, meta) for det in detections]


def _best_zone_hit(
    detections: list[Detection],
    *,
    param: ParamGroup,
    frame_size: tuple[int, int],
    anchor_mode: str,
) -> ZoneHit:
    frame_w, frame_h = frame_size
    ref_size = (param.ref_width, param.ref_height)
    hit: ZoneHit = None

    for det in detections:
        zone = judge_zone(
            det.as_box(),
            slow_polygon=param.slow_polygon,
            stop_polygon=param.stop_polygon,
            ref_size=ref_size,
            frame_size=(frame_w, frame_h),
            anchor_mode=anchor_mode,  # type: ignore[arg-type]
            min_overlap=param.min_overlap,
        )
        if zone == "stop":
            return "stop"
        if zone == "slow":
            hit = "slow"
    return hit


def infer_raw(
    frame: np.ndarray,
    *,
    backend: InferBackend,
) -> tuple[np.ndarray, LetterboxMeta]:
    """Letterbox + backend infer once; shared by multi-station fan-out (#34)."""
    batch, meta = preprocess_bgr(frame, input_size=backend.input_size)
    raw = backend.infer_batch(batch)
    return raw, meta


@dataclass
class StationRunner:
    station: StationConfig
    param: ParamGroup
    fsm: IntrusionFSM = field(init=False)
    hold: DetectionHold = field(init=False)

    def __post_init__(self) -> None:
        self.fsm = IntrusionFSM(
            enter_frames=self.param.enter_frames,
            exit_frames=self.param.exit_frames,
        )
        self.hold = DetectionHold(hold_ms=float(self.param.hold_ms))

    def process_from_raw(
        self,
        raw: np.ndarray,
        meta: LetterboxMeta,
        *,
        frame_size: tuple[int, int],
        timestamp_ms: float,
    ) -> tuple[int, ZoneHit, list[Detection], bool]:
        """Per-station postprocess / zone / FSM from a shared infer result."""
        letterbox_dets = postprocess_yolo(
            raw,
            conf=self.param.conf,
            nms_iou=self.param.nms_iou,
            min_area=self.param.min_box_area,
            class_ids=(0,),
        )
        detections = scale_detections_to_frame(letterbox_dets, meta)
        detections = self.hold.apply(detections, timestamp_ms)

        frame_w, frame_h = frame_size
        zone_hit = _best_zone_hit(
            detections,
            param=self.param,
            frame_size=(frame_w, frame_h),
            anchor_mode=self.station.detect_mode,
        )
        signal = self.fsm.update(zone_hit)
        return signal, zone_hit, detections, False

    def process(
        self,
        frame: np.ndarray,
        *,
        backend: InferBackend,
        frame_index: int,
        timestamp_ms: float,
    ) -> tuple[int, ZoneHit, list[Detection], bool]:
        del frame_index  # kept for API compatibility with callers
        raw, meta = infer_raw(frame, backend=backend)
        frame_h, frame_w = frame.shape[:2]
        return self.process_from_raw(
            raw,
            meta,
            frame_size=(frame_w, frame_h),
            timestamp_ms=timestamp_ms,
        )

    def set_fault(self, fault: bool) -> int:
        self.fsm.set_fault(fault)
        if fault:
            self.hold.reset()
        return self.fsm.update(None)


def resolve_station(config: AppConfig, station_id: str | None) -> tuple[StationConfig, ParamGroup]:
    """Return the enabled station and its param group."""
    return _resolve_station(config, station_id)


def _resolve_station(config: AppConfig, station_id: str | None) -> tuple[StationConfig, ParamGroup]:
    stations = [st for st in config.stations if st.enabled]
    if station_id:
        stations = [st for st in stations if st.id == station_id]
    if not stations:
        raise ValueError("no enabled station found in config")

    station = stations[0]
    param_map = {pg.id: pg for pg in config.param_groups}
    param = param_map.get(station.param_group_id)
    if param is None:
        raise ValueError(f"unknown param_group_id: {station.param_group_id!r}")
    return station, param


def run_video_file(
    *,
    video_path: str | Path,
    backend: InferBackend,
    config: AppConfig | str | Path,
    station_id: str | None = None,
    max_frames: int | None = None,
    fps: float = 15.0,
) -> tuple[list[int], StationRunner]:
    """Process a video file and return per-frame signal sequence."""
    from camera.video_file import VideoFileStream

    if not isinstance(config, AppConfig):
        config = load_config(config)

    station, param = _resolve_station(config, station_id)
    runner = StationRunner(station=station, param=param)

    stream = VideoFileStream(video_path, loop=False)
    stream.start()

    signals: list[int] = []
    frame_index = 0
    frame_interval_ms = 1000.0 / fps if fps > 0 else 0.0

    try:
        while max_frames is None or frame_index < max_frames:
            frame = stream.get_frame()
            if frame is None:
                break

            timestamp_ms = frame_index * frame_interval_ms
            signal, _zone, _dets, _fault = runner.process(
                frame,
                backend=backend,
                frame_index=frame_index,
                timestamp_ms=timestamp_ms,
            )
            signals.append(signal)
            frame_index += 1
    finally:
        stream.stop()

    return signals, runner
