"""Tests for camera source resolution."""

from __future__ import annotations

from pathlib import Path

from app.camera_source import resolve_video_path, video_loop_for_station
from core.config import load_config


def test_resolve_video_fallback_to_replay() -> None:
    config = load_config(Path("configs/config.example.json"))
    station = config.stations[0]
    path = resolve_video_path(config, station, root=Path.cwd())
    assert path.name == "demo.mp4"
    assert video_loop_for_station(config, station) is True
