"""USB camera capture via GStreamer (Jetson) or V4L2 OpenCV."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import numpy as np

from camera.base import CameraStream, ConnectionCallback, SourceType

logger = logging.getLogger(__name__)

CaptureFactory = Callable[[], object]


def _gstreamer_pipeline(
    device: str,
    *,
    width: int | None,
    height: int | None,
    fps: int | None,
) -> str:
    caps = "video/x-raw"
    if width is not None and height is not None:
        caps += f",width={width},height={height}"
    if fps is not None:
        caps += f",framerate={fps}/1"
    return (
        f"v4l2src device={device} ! {caps} ! "
        "videoconvert ! video/x-raw,format=BGR ! "
        "appsink drop=true max-buffers=1 sync=false"
    )


class V4L2UsbStream(CameraStream):
    """Live USB camera stream with latest-frame buffer, watchdog, and auto-reconnect."""

    def __init__(
        self,
        device: str = "/dev/video0",
        *,
        width: int | None = None,
        height: int | None = None,
        fps: int | None = None,
        use_gstreamer: bool = True,
        watchdog_ms: int = 3000,
        reconnect_interval_ms: int = 1000,
        capture_factory: CaptureFactory | None = None,
    ) -> None:
        self._device = device
        self._width = width
        self._height = height
        self._fps = fps
        self._use_gstreamer = use_gstreamer
        self._watchdog_ms = watchdog_ms
        self._reconnect_interval_ms = reconnect_interval_ms
        self._capture_factory = capture_factory

        self._capture: object | None = None
        self._running = False
        self._connected = False
        self._connection_callback: ConnectionCallback | None = None
        self._latest_frame: np.ndarray | None = None
        self._last_frame_monotonic = 0.0
        self._frame_lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._watchdog_thread: threading.Thread | None = None

    @property
    def source_type(self) -> SourceType:
        return SourceType.USB

    @property
    def connected(self) -> bool:
        return self._connected

    def on_connection_changed(self, callback: ConnectionCallback) -> None:
        self._connection_callback = callback

    def start(self) -> None:
        if self._running:
            return
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop,
            name=f"v4l2-usb-{self._device}",
            daemon=True,
        )
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            name=f"v4l2-usb-watchdog-{self._device}",
            daemon=True,
        )
        self._thread.start()
        self._watchdog_thread.start()

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=5.0)
            self._watchdog_thread = None
        self._release_capture()
        with self._frame_lock:
            self._latest_frame = None
        self._set_connected(False)

    def get_frame(self) -> np.ndarray | None:
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def _set_connected(self, connected: bool) -> None:
        if self._connected == connected:
            return
        self._connected = connected
        callback = self._connection_callback
        if callback is not None:
            try:
                callback(connected)
            except Exception:
                logger.exception("connection callback failed")

    def _open_capture(self) -> object | None:
        if self._capture_factory is not None:
            capture = self._capture_factory()
            if capture is not None and capture.isOpened():
                return capture
            if capture is not None:
                capture.release()
            return None

        import cv2

        if self._use_gstreamer:
            pipeline = _gstreamer_pipeline(
                self._device,
                width=self._width,
                height=self._height,
                fps=self._fps,
            )
            capture = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
            if capture.isOpened():
                return capture
            capture.release()
            logger.warning(
                "GStreamer open failed for %s, falling back to V4L2",
                self._device,
            )

        capture = cv2.VideoCapture(self._device, cv2.CAP_V4L2)
        if capture.isOpened():
            return capture
        capture.release()
        return None

    def _release_capture(self) -> None:
        with self._io_lock:
            if self._capture is not None:
                self._capture.release()
                self._capture = None

    def _store_frame(self, frame: np.ndarray) -> None:
        with self._frame_lock:
            self._latest_frame = frame
        self._last_frame_monotonic = time.monotonic()
        self._set_connected(True)

    def _clear_frame(self) -> None:
        with self._frame_lock:
            self._latest_frame = None

    def _watchdog_expired(self) -> bool:
        if self._last_frame_monotonic <= 0.0:
            return False
        elapsed_ms = (time.monotonic() - self._last_frame_monotonic) * 1000.0
        return elapsed_ms > self._watchdog_ms

    def _handle_disconnect(self) -> None:
        self._release_capture()
        self._clear_frame()
        self._set_connected(False)

    def _watchdog_loop(self) -> None:
        poll_sec = max(self._watchdog_ms / 4.0, 50.0) / 1000.0
        while self._running and not self._stop_event.wait(poll_sec):
            with self._io_lock:
                if self._capture is None:
                    continue
            if not self._watchdog_expired():
                continue
            logger.warning("USB camera watchdog expired: %s", self._device)
            self._handle_disconnect()

    def _capture_loop(self) -> None:
        reconnect_sec = self._reconnect_interval_ms / 1000.0
        while self._running and not self._stop_event.is_set():
            with self._io_lock:
                capture = self._capture
            if capture is None:
                opened = self._open_capture()
                with self._io_lock:
                    self._capture = opened
                if opened is None:
                    self._clear_frame()
                    self._set_connected(False)
                    if self._stop_event.wait(reconnect_sec):
                        break
                    continue
                self._last_frame_monotonic = time.monotonic()

            with self._io_lock:
                capture = self._capture
            if capture is None:
                continue

            ok, frame = capture.read()
            if not ok or frame is None:
                logger.warning("USB camera read failed: %s", self._device)
                self._handle_disconnect()
                if self._stop_event.wait(reconnect_sec):
                    break
                continue

            self._store_frame(frame)
            time.sleep(0.001)
