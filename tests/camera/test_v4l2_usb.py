"""Unit tests for V4L2UsbStream (mocked capture; no /dev/video* required)."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pytest

from camera.base import SourceType
from camera.v4l2_usb import V4L2UsbStream, _gstreamer_pipeline


class _FakeCapture:
    """Minimal cv2.VideoCapture stand-in for tests."""

    def __init__(
        self,
        *,
        opened: bool = True,
        frames: list[np.ndarray] | None = None,
        fail_reads: int = 0,
    ) -> None:
        self._opened = opened
        self._frames = list(frames or [])
        self._fail_reads = fail_reads
        self._read_idx = 0
        self.released = False

    def isOpened(self) -> bool:
        return self._opened

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._fail_reads > 0:
            self._fail_reads -= 1
            return False, None
        if self._read_idx >= len(self._frames):
            return False, None
        frame = self._frames[self._read_idx]
        self._read_idx += 1
        return True, frame

    def release(self) -> None:
        self._opened = False
        self.released = True


def _solid_frame(value: int, shape: tuple[int, int, int] = (4, 4, 3)) -> np.ndarray:
    return np.full(shape, value, dtype=np.uint8)


def _wait_until(predicate: Any, *, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met before timeout")


def test_source_type_is_usb() -> None:
    stream = V4L2UsbStream("/dev/video0")
    assert stream.source_type is SourceType.USB


def test_gstreamer_pipeline_includes_device_and_caps() -> None:
    pipeline = _gstreamer_pipeline(
        "/dev/video0",
        width=640,
        height=480,
        fps=30,
    )
    assert "v4l2src device=/dev/video0" in pipeline
    assert "width=640,height=480" in pipeline
    assert "framerate=30/1" in pipeline
    assert "appsink drop=true max-buffers=1" in pipeline


def test_get_frame_returns_copy_not_view() -> None:
    frame = _solid_frame(7)
    fake = _FakeCapture(frames=[frame] * 5)

    def factory() -> _FakeCapture:
        return fake

    stream = V4L2UsbStream(
        "/dev/video0",
        capture_factory=factory,
        watchdog_ms=10_000,
    )
    stream.start()
    try:
        _wait_until(lambda: stream.get_frame() is not None)
        first = stream.get_frame()
        assert first is not None
        first[0, 0, 0] = 99
        second = stream.get_frame()
        assert second is not None
        assert second[0, 0, 0] == 7
    finally:
        stream.stop()


def test_get_frame_none_before_start() -> None:
    stream = V4L2UsbStream("/dev/video0", capture_factory=lambda: _FakeCapture())
    assert stream.get_frame() is None


def test_connection_callback_on_connect_and_disconnect() -> None:
    frame = _solid_frame(3)
    fake = _FakeCapture(frames=[frame])

    stream = V4L2UsbStream(
        "/dev/video0",
        capture_factory=lambda: fake,
        watchdog_ms=10_000,
        reconnect_interval_ms=50,
    )
    events: list[bool] = []
    stream.on_connection_changed(events.append)
    stream.start()
    try:
        _wait_until(lambda: True in events)
        assert stream.connected is True
        _wait_until(lambda: False in events, timeout=3.0)
        assert stream.connected is False
    finally:
        stream.stop()


def test_watchdog_marks_disconnected_on_stale_frames() -> None:
    frame = _solid_frame(1)

    class _HungCapture(_FakeCapture):
        def read(self) -> tuple[bool, np.ndarray | None]:
            if self._read_idx == 0:
                self._read_idx += 1
                return True, frame
            time.sleep(5.0)
            return False, None

    stream = V4L2UsbStream(
        "/dev/video0",
        capture_factory=lambda: _HungCapture(),
        watchdog_ms=80,
        reconnect_interval_ms=50,
    )
    events: list[bool] = []
    stream.on_connection_changed(events.append)
    stream.start()
    try:
        _wait_until(lambda: True in events)
        _wait_until(lambda: False in events, timeout=3.0)
        assert stream.connected is False
    finally:
        stream.stop()


def test_open_failure_stays_disconnected_until_device_available() -> None:
    state = {"opened": False}

    def factory() -> _FakeCapture:
        if not state["opened"]:
            return _FakeCapture(opened=False)
        return _FakeCapture(frames=[_solid_frame(5)] * 100)

    stream = V4L2UsbStream(
        "/dev/video0",
        capture_factory=factory,
        reconnect_interval_ms=50,
        watchdog_ms=10_000,
    )
    events: list[bool] = []
    stream.on_connection_changed(events.append)
    stream.start()
    try:
        time.sleep(0.15)
        assert stream.connected is False
        assert stream.get_frame() is None

        state["opened"] = True
        _wait_until(lambda: stream.get_frame() is not None)
        assert True in events
        assert stream.connected is True
    finally:
        stream.stop()


@pytest.mark.skipif(
    not __import__("pathlib").Path("/dev/video0").exists(),
    reason="no V4L2 device on this board",
)
def test_real_device_smoke_if_present() -> None:
    stream = V4L2UsbStream("/dev/video0", use_gstreamer=True, watchdog_ms=5000)
    stream.start()
    try:
        _wait_until(lambda: stream.get_frame() is not None, timeout=5.0)
        frame = stream.get_frame()
        assert frame is not None
        assert frame.ndim == 3
        assert frame.dtype == np.uint8
    finally:
        stream.stop()
