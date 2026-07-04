"""Resolve camera / video source for a station."""

from __future__ import annotations

from pathlib import Path

from core.config import AppConfig, CameraConfig, StationConfig


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
