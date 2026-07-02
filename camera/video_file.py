"""
Recorded video file as a CameraStream (D2: import video for detection).

Implementation stub for phase 2; interface defined for pipeline integration.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from camera.base import CameraStream, SourceType


class VideoFileStream(CameraStream):
    """Read frames from a video file; optional loop for replay debugging."""

    def __init__(self, path: str | Path, *, loop: bool = True) -> None:
        self._path = Path(path)
        self._loop = loop
        self._capture = None
        self._running = False

    @property
    def source_type(self) -> SourceType:
        return SourceType.VIDEO_FILE

    def start(self) -> None:
        if not self._path.is_file():
            raise FileNotFoundError(f"Video not found: {self._path}")
        import cv2

        self._capture = cv2.VideoCapture(str(self._path))
        if not self._capture.isOpened():
            raise RuntimeError(f"Failed to open video: {self._path}")
        self._running = True

    def stop(self) -> None:
        self._running = False
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def get_frame(self) -> np.ndarray | None:
        if not self._running or self._capture is None:
            return None
        ok, frame = self._capture.read()
        if not ok:
            if self._loop:
                self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self._capture.read()
            if not ok:
                return None
        return frame.copy()
