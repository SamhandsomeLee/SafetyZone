"""Tests for record.event_recorder."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from core.config import RecordConfig
from record.event_recorder import EventRecorder, SnapshotEvent


def _bgr_frame(*, width: int = 64, height: int = 48, color: tuple[int, int, int] = (10, 20, 30)) -> np.ndarray:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:] = color
    return frame


def _is_jpeg(path: Path) -> bool:
    data = path.read_bytes()
    return len(data) >= 2 and data[0] == 0xFF and data[1] == 0xD8


def _make_recorder(
    tmp_path: Path,
    *,
    snapshot: bool = True,
    save_on_slow: bool = False,
    max_snapshots: int = 100,
    station_id: str = "station0",
) -> EventRecorder:
    config = RecordConfig(snapshot=snapshot)
    return EventRecorder(
        config=config,
        output_dir=tmp_path / "records",
        station_id=station_id,
        save_on_slow=save_on_slow,
        max_snapshots=max_snapshots,
    )


def test_stop_edge_saves_jpeg(tmp_path: Path) -> None:
    recorder = _make_recorder(tmp_path)
    frame = _bgr_frame()

    assert recorder.on_signal(-1, frame) is None
    assert recorder.on_signal(0, frame) is None

    event = recorder.on_signal(2, frame, timestamp=1_700_000_000.0)
    assert event is not None
    assert isinstance(event, SnapshotEvent)
    assert event.kind == "stop"
    assert event.signal == 2
    assert event.station_id == "station0"
    assert event.path.name == "snapshot.jpg"
    assert event.path.parent.name.endswith("_stop")
    assert event.path.is_file()
    assert _is_jpeg(event.path)

    decoded = cv2.imread(str(event.path))
    assert decoded is not None
    assert decoded.shape == frame.shape


def test_slow_edge_optional(tmp_path: Path) -> None:
    recorder = _make_recorder(tmp_path, save_on_slow=True)
    frame = _bgr_frame(color=(40, 50, 60))

    assert recorder.on_signal(1, frame, timestamp=1_700_000_001.0) is not None
    slow_path = recorder.output_dir / "station0"
    slow_dirs = list(slow_path.glob("*_slow"))
    assert len(slow_dirs) == 1
    assert _is_jpeg(slow_dirs[0] / "snapshot.jpg")

    # STOP rising edge should save a separate snapshot, not duplicate SLOW.
    stop_event = recorder.on_signal(2, frame, timestamp=1_700_000_002.0)
    assert stop_event is not None
    assert stop_event.kind == "stop"
    assert len(list(slow_path.glob("*_stop"))) == 1


def test_no_snapshot_when_disabled(tmp_path: Path) -> None:
    recorder = _make_recorder(tmp_path, snapshot=False)
    frame = _bgr_frame()

    assert recorder.on_signal(2, frame) is None
    assert not (tmp_path / "records").exists()


def test_clear_edge_does_not_trigger(tmp_path: Path) -> None:
    recorder = _make_recorder(tmp_path)
    frame = _bgr_frame()

    recorder.on_signal(2, frame)
    assert recorder.on_signal(-1, frame) is None
    assert len(list((tmp_path / "records" / "station0").iterdir())) == 1


def test_same_level_does_not_repeat(tmp_path: Path) -> None:
    recorder = _make_recorder(tmp_path)
    frame = _bgr_frame()

    recorder.on_signal(2, frame)
    assert recorder.on_signal(2, frame) is None
    assert len(list((tmp_path / "records" / "station0").iterdir())) == 1


def test_retention_removes_oldest_events(tmp_path: Path) -> None:
    recorder = _make_recorder(tmp_path, max_snapshots=2)
    frame = _bgr_frame()

    recorder.on_signal(2, frame, timestamp=100.0)
    recorder.reset()
    recorder.on_signal(2, frame, timestamp=200.0)
    recorder.reset()
    recorder.on_signal(2, frame, timestamp=300.0)

    station_root = tmp_path / "records" / "station0"
    event_dirs = sorted(station_root.iterdir(), key=lambda p: p.stat().st_mtime)
    assert len(event_dirs) == 2
    names = {p.name for p in event_dirs}
    assert "19700101T000140_000_stop" not in names
    assert all(_is_jpeg(p / "snapshot.jpg") for p in event_dirs)


def test_custom_output_dir_and_station(tmp_path: Path) -> None:
    out = tmp_path / "custom" / "alarm_dir"
    config = RecordConfig(snapshot=True)
    recorder = EventRecorder(
        config=config,
        output_dir=out,
        station_id="line_a",
        max_snapshots=5,
    )
    frame = _bgr_frame()

    event = recorder.on_signal(2, frame, timestamp=1_700_000_010.0)
    assert event is not None
    assert event.path.is_relative_to(out / "line_a")


def test_reset_allows_retrigger(tmp_path: Path) -> None:
    recorder = _make_recorder(tmp_path)
    frame = _bgr_frame()

    recorder.on_signal(2, frame, timestamp=10.0)
    recorder.on_signal(-1, frame)
    recorder.reset()
    event = recorder.on_signal(2, frame, timestamp=20.0)
    assert event is not None
    assert len(list((tmp_path / "records" / "station0").iterdir())) == 2


def test_invalid_frame_rejected(tmp_path: Path) -> None:
    recorder = _make_recorder(tmp_path)
    bad = np.zeros((8, 8), dtype=np.uint8)

    with pytest.raises(ValueError, match="BGR"):
        recorder.on_signal(2, bad)
