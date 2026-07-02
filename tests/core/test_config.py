"""Tests for core.config."""

import json
from pathlib import Path

import pytest

from core.config import AppConfig, CameraConfig, ConfigError, ParamGroup, StationConfig, load_config, save_config


def test_load_example_config():
    cfg = load_config(Path("configs/config.example.json"))
    assert len(cfg.cameras) == 2
    assert len(cfg.stations) == 1
    assert cfg.stations[0].detect_mode == "person"
    assert cfg.param_groups[0].enter_frames == 2


def test_duplicate_station_id_raises(tmp_path: Path):
    data = {
        "cameras": [{"id": "c0", "source_type": "usb", "device": "/dev/video0"}],
        "param_groups": [
            {
                "id": "pg0",
                "ref_width": 640,
                "ref_height": 480,
                "slow_polygon": [[0, 0], [640, 0], [640, 480]],
                "stop_polygon": [[100, 100], [200, 100], [200, 200]],
            }
        ],
        "stations": [
            {"id": "s0", "camera_id": "c0", "param_group_id": "pg0"},
            {"id": "s0", "camera_id": "c0", "param_group_id": "pg0"},
        ],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="duplicate station"):
        load_config(path)


def test_video_file_requires_path(tmp_path: Path):
    data = {
        "cameras": [{"id": "v0", "source_type": "video_file"}],
        "param_groups": [],
        "stations": [],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="requires 'path'"):
        load_config(path)


def test_unknown_camera_reference(tmp_path: Path):
    data = {
        "cameras": [{"id": "c0", "source_type": "usb", "device": "/dev/video0"}],
        "param_groups": [
            {
                "id": "pg0",
                "ref_width": 640,
                "ref_height": 480,
                "slow_polygon": [[0, 0], [640, 0], [640, 480]],
                "stop_polygon": [[100, 100], [200, 100], [200, 200]],
            }
        ],
        "stations": [{"id": "s0", "camera_id": "missing", "param_group_id": "pg0"}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown camera_id"):
        load_config(path)


def test_non_person_detect_mode_rejected(tmp_path: Path):
    data = {
        "cameras": [{"id": "c0", "source_type": "usb", "device": "/dev/video0"}],
        "param_groups": [
            {
                "id": "pg0",
                "ref_width": 640,
                "ref_height": 480,
                "slow_polygon": [[0, 0], [640, 0], [640, 480]],
                "stop_polygon": [[100, 100], [200, 100], [200, 200]],
            }
        ],
        "stations": [
            {"id": "s0", "camera_id": "c0", "param_group_id": "pg0", "detect_mode": "object"}
        ],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="only detect_mode 'person'"):
        load_config(path)


def test_corrupt_json_falls_back_to_backup(tmp_path: Path):
    cfg_path = tmp_path / "config.json"
    good = {
        "cameras": [{"id": "c0", "source_type": "usb", "device": "/dev/video0"}],
        "param_groups": [
            {
                "id": "pg0",
                "ref_width": 640,
                "ref_height": 480,
                "slow_polygon": [[0, 0], [640, 0], [640, 480]],
                "stop_polygon": [[100, 100], [200, 100], [200, 200]],
            }
        ],
        "stations": [{"id": "s0", "camera_id": "c0", "param_group_id": "pg0"}],
    }
    cfg_path.write_text(json.dumps(good), encoding="utf-8")
    backup = tmp_path / "config.json.bak.20260101_120000"
    backup.write_text(json.dumps(good), encoding="utf-8")

    cfg_path.write_text("{ not valid json", encoding="utf-8")
    loaded = load_config(cfg_path)
    assert loaded.stations[0].id == "s0"


def test_save_config_atomic_with_backup(tmp_path: Path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text('{"cameras":[],"param_groups":[],"stations":[]}', encoding="utf-8")

    config = AppConfig(
        cameras=[CameraConfig(id="c0", source_type="usb", device="/dev/video0")],
        param_groups=[
            ParamGroup(
                id="pg0",
                ref_width=640,
                ref_height=480,
                slow_polygon=[[0, 0], [640, 0], [640, 480]],
                stop_polygon=[[100, 100], [200, 100], [200, 200]],
            )
        ],
        stations=[
            StationConfig(id="s0", camera_id="c0", param_group_id="pg0", detect_mode="person")
        ],
    )
    save_config(config, cfg_path)

    reloaded = load_config(cfg_path)
    assert reloaded.cameras[0].id == "c0"
    backups = list(tmp_path.glob("config.json.bak.*"))
    assert len(backups) == 1
