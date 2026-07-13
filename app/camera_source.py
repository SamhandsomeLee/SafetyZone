"""Resolve camera / video source for a station."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from camera.base import CameraStream
from camera.video_file import VideoFileStream
from camera.v4l2_usb import V4L2UsbStream
from core.config import AppConfig, CameraConfig, StationConfig


@dataclass(frozen=True)
class OpenedSource:
    """Result of opening a station camera (may be degraded to video_file)."""

    stream: CameraStream
    requested: CameraConfig
    effective: CameraConfig
    degraded: bool
    message: str | None = None


def camera_for_station(config: AppConfig, station: StationConfig) -> CameraConfig:
    cam_map = {cam.id: cam for cam in config.cameras}
    cam = cam_map.get(station.camera_id)
    if cam is None:
        raise ValueError(f"unknown camera_id: {station.camera_id!r}")
    return cam


def resolve_video_path(config: AppConfig, station: StationConfig, *, root: Path | None = None) -> Path:
    """
    Return a video file path for Bootstrap preview.

    Uses the station's camera when it is ``video_file``; otherwise the first
    ``video_file`` entry in config (typical Bootstrap: station on USB, demo on replay0).
    """
    root = root or Path.cwd()
    cam = camera_for_station(config, station)
    if cam.source_type == "video_file" and cam.path:
        path = Path(cam.path)
        if not path.is_absolute():
            path = root / path
        return path

    for candidate in config.cameras:
        if candidate.source_type == "video_file" and candidate.path:
            path = Path(candidate.path)
            if not path.is_absolute():
                path = root / path
            return path

    raise ValueError("no video_file camera configured")


def video_loop_for_station(config: AppConfig, station: StationConfig) -> bool:
    cam = camera_for_station(config, station)
    if cam.source_type == "video_file":
        return cam.loop
    for candidate in config.cameras:
        if candidate.source_type == "video_file":
            return candidate.loop
    return True


def _first_video_file_camera(config: AppConfig) -> CameraConfig | None:
    for candidate in config.cameras:
        if candidate.source_type == "video_file" and candidate.path:
            return candidate
    return None


def _video_stream_for_camera(
    cam: CameraConfig,
    *,
    root: Path,
) -> VideoFileStream:
    if not cam.path:
        raise ValueError(f"video_file camera {cam.id!r} missing path")
    path = Path(cam.path)
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        raise FileNotFoundError(f"video not found: {path}")
    return VideoFileStream(path, loop=cam.loop)


def open_source_for_station(
    config: AppConfig,
    station: StationConfig,
    *,
    root: Path | None = None,
) -> OpenedSource:
    """
    Build a CameraStream for the station's configured camera.

    USB without a present device (or later open failure handled by caller) falls
    back to the first video_file camera when available.
    """
    root = root or Path.cwd()
    requested = camera_for_station(config, station)

    if requested.source_type == "video_file":
        stream = _video_stream_for_camera(requested, root=root)
        return OpenedSource(
            stream=stream,
            requested=requested,
            effective=requested,
            degraded=False,
            message=None,
        )

    if requested.source_type == "usb":
        device = requested.device or "/dev/video0"
        if Path(device).exists():
            stream = V4L2UsbStream(device=device)
            return OpenedSource(
                stream=stream,
                requested=requested,
                effective=requested,
                degraded=False,
                message=None,
            )

        fallback = _first_video_file_camera(config)
        if fallback is None:
            raise FileNotFoundError(
                f"USB device {device!r} unavailable and no video_file fallback configured"
            )
        stream = _video_stream_for_camera(fallback, root=root)
        msg = f"USB {device} 不可用，已降级到 {fallback.id}（{fallback.label or fallback.path}）"
        return OpenedSource(
            stream=stream,
            requested=requested,
            effective=fallback,
            degraded=True,
            message=msg,
        )

    raise ValueError(f"unsupported source_type: {requested.source_type!r}")
