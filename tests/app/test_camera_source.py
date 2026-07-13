"""Tests for camera source resolution and open factory."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.camera_source import (
    open_source_for_station,
    resolve_video_path,
    video_loop_for_station,
)
from camera.base import SourceType
from camera.video_file import VideoFileStream
from core.config import (
    AppConfig,
    CameraConfig,
    ParamGroup,
    StationConfig,
    load_config,
)


def test_resolve_video_fallback_to_replay() -> None:
    config = load_config(Path("configs/config.example.json"))
    station = config.stations[0]
    path = resolve_video_path(config, station, root=Path.cwd())
    assert path.name == "demo.mp4"
    assert video_loop_for_station(config, station) is True


def _minimal_config(*, usb_device: str, video_path: str) -> AppConfig:
    return AppConfig(
        cameras=[
            CameraConfig(
                id="cam0",
                source_type="usb",
                device=usb_device,
                label="USB",
            ),
            CameraConfig(
                id="replay0",
                source_type="video_file",
                path=video_path,
                loop=True,
                label="replay",
            ),
        ],
        param_groups=[
            ParamGroup(
                id="default",
                ref_width=640,
                ref_height=480,
                slow_polygon=[[0, 0], [10, 0], [10, 10]],
                stop_polygon=[[1, 1], [5, 1], [5, 5]],
            )
        ],
        stations=[
            StationConfig(
                id="station0",
                camera_id="cam0",
                param_group_id="default",
            )
        ],
    )


def test_open_video_file_source(tmp_path: Path) -> None:
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"not-a-real-mp4-but-exists")
    # VideoFileStream.start would fail on bad file; factory only constructs.
    config = _minimal_config(usb_device="/dev/null_missing", video_path=str(video))
    config.stations[0].camera_id = "replay0"
    station = config.stations[0]
    opened = open_source_for_station(config, station, root=tmp_path)
    assert opened.degraded is False
    assert opened.effective.id == "replay0"
    assert isinstance(opened.stream, VideoFileStream)
    assert opened.stream.source_type == SourceType.VIDEO_FILE


def test_open_usb_missing_degrades_to_video(tmp_path: Path) -> None:
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"x")
    config = _minimal_config(
        usb_device=str(tmp_path / "no_such_video_device"),
        video_path=str(video),
    )
    opened = open_source_for_station(config, config.stations[0], root=tmp_path)
    assert opened.degraded is True
    assert opened.requested.id == "cam0"
    assert opened.effective.id == "replay0"
    assert opened.message is not None
    assert "降级" in opened.message
    assert isinstance(opened.stream, VideoFileStream)


def test_open_usb_missing_without_fallback_raises(tmp_path: Path) -> None:
    config = AppConfig(
        cameras=[
            CameraConfig(
                id="cam0",
                source_type="usb",
                device=str(tmp_path / "missing"),
            )
        ],
        param_groups=[
            ParamGroup(
                id="default",
                ref_width=640,
                ref_height=480,
                slow_polygon=[[0, 0], [10, 0], [10, 10]],
                stop_polygon=[[1, 1], [5, 1], [5, 5]],
            )
        ],
        stations=[
            StationConfig(id="station0", camera_id="cam0", param_group_id="default")
        ],
    )
    with pytest.raises(FileNotFoundError, match="no video_file fallback"):
        open_source_for_station(config, config.stations[0], root=tmp_path)
