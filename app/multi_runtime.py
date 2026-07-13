"""Multi-station runtime: one infer per camera, fan-out to stations (#34)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.pipeline import StationRunner, infer_raw
from core.config import AppConfig, ParamGroup, StationConfig, get_param_group
from core.postprocess import Detection
from core.zone import ZoneHit
from detect.backend import InferBackend


@dataclass(frozen=True)
class StationFrameResult:
    """Per-station outcome for one shared camera frame."""

    station_id: str
    camera_id: str
    signal: int
    zone_hit: ZoneHit
    detections: tuple[Detection, ...]
    fault: bool


def enabled_stations(config: AppConfig) -> list[StationConfig]:
    return [st for st in config.stations if st.enabled]


def group_stations_by_camera(config: AppConfig) -> dict[str, list[StationConfig]]:
    """Map camera_id → enabled stations sharing that camera (order preserved)."""
    groups: dict[str, list[StationConfig]] = {}
    for st in enabled_stations(config):
        groups.setdefault(st.camera_id, []).append(st)
    return groups


def build_runners(config: AppConfig) -> dict[str, StationRunner]:
    """station_id → StationRunner for all enabled stations."""
    runners: dict[str, StationRunner] = {}
    for st in enabled_stations(config):
        param = get_param_group(config, st.param_group_id)
        runners[st.id] = StationRunner(station=st, param=param)
    return runners


class MultiStationRuntime:
    """
    Own StationRunners grouped by camera_id.

    ``process_camera_frame`` runs TensorRT/ONNX infer **once** per call, then
    independently postprocesses / judges / updates FSM for each station on that camera.
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._runners = build_runners(config)
        self._by_camera = group_stations_by_camera(config)

    @property
    def camera_ids(self) -> list[str]:
        return list(self._by_camera.keys())

    def stations_for_camera(self, camera_id: str) -> list[StationConfig]:
        return list(self._by_camera.get(camera_id, ()))

    def runner(self, station_id: str) -> StationRunner:
        try:
            return self._runners[station_id]
        except KeyError as exc:
            raise KeyError(f"unknown or disabled station_id: {station_id!r}") from exc

    def reload_param(self, station_id: str, param: ParamGroup) -> None:
        """Hot-update param group for one station (rebuild FSM/hold from new thresholds)."""
        from core.fsm import IntrusionFSM
        from core.tracking import DetectionHold

        runner = self.runner(station_id)
        runner.param = param
        runner.fsm = IntrusionFSM(
            enter_frames=param.enter_frames,
            exit_frames=param.exit_frames,
        )
        runner.hold = DetectionHold(hold_ms=float(param.hold_ms))

    def process_camera_frame(
        self,
        camera_id: str,
        frame: np.ndarray,
        *,
        backend: InferBackend,
        frame_index: int,
        timestamp_ms: float,
    ) -> list[StationFrameResult]:
        """
        Infer once for *camera_id*, fan-out to all stations bound to it.

        Raises ValueError if no enabled station uses *camera_id*.
        """
        del frame_index  # reserved for callers / future metrics
        stations = self._by_camera.get(camera_id)
        if not stations:
            raise ValueError(f"no enabled station for camera_id={camera_id!r}")

        raw, meta = infer_raw(frame, backend=backend)
        frame_h, frame_w = frame.shape[:2]
        frame_size = (frame_w, frame_h)

        results: list[StationFrameResult] = []
        for st in stations:
            runner = self._runners[st.id]
            signal, zone_hit, detections, fault = runner.process_from_raw(
                raw,
                meta,
                frame_size=frame_size,
                timestamp_ms=timestamp_ms,
            )
            results.append(
                StationFrameResult(
                    station_id=st.id,
                    camera_id=camera_id,
                    signal=signal,
                    zone_hit=zone_hit,
                    detections=tuple(detections),
                    fault=fault,
                )
            )
        return results
