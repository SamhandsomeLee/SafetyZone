"""Unified frame source: USB live stream or recorded video file."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Callable

import numpy as np


class SourceType(str, Enum):
    USB = "usb"
    VIDEO_FILE = "video_file"


ConnectionCallback = Callable[[bool], None]


class CameraStream(ABC):
    """Abstract frame source shared by USB and video-file backends."""

    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        ...

    @abstractmethod
    def start(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...

    @abstractmethod
    def get_frame(self) -> np.ndarray | None:
        """Return latest frame copy, or None if unavailable."""
        ...

    @property
    def connected(self) -> bool:
        return True

    def on_connection_changed(self, callback: ConnectionCallback) -> None:
        """Optional: register connect/disconnect handler (USB watchdog)."""
        self._connection_callback = callback
