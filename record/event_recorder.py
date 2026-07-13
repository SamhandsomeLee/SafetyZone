"""Alarm-edge snapshot recorder (STOP / optional SLOW)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np

from core.config import RecordConfig

logger = logging.getLogger(__name__)

SignalKind = Literal["stop", "slow"]
SIGNAL_STOP = 2
SIGNAL_SLOW = 1


@dataclass(frozen=True)
class SnapshotEvent:
    """Metadata for a persisted alarm snapshot."""

    station_id: str
    kind: SignalKind
    signal: int
    path: Path
    timestamp: float


class EventRecorder:
    """
    Persist JPEG snapshots on rising STOP (and optional SLOW) signal edges.

    Intended to be called once per processed frame from the inference/pipeline
    thread (Wave2 wiring); this module does not subscribe to workers itself.
    """

    def __init__(
        self,
        *,
        config: RecordConfig,
        output_dir: str | Path,
        station_id: str,
        save_on_slow: bool = False,
        max_snapshots: int = 100,
    ) -> None:
        if max_snapshots < 1:
            raise ValueError("max_snapshots must be >= 1")
        self._config = config
        self._output_dir = Path(output_dir)
        self._station_id = station_id
        self._save_on_slow = save_on_slow
        self._max_snapshots = max_snapshots
        self._prev_signal = -1

    @property
    def station_id(self) -> str:
        return self._station_id

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    def reset(self) -> None:
        """Clear edge tracking (e.g. when a station run stops)."""
        self._prev_signal = -1

    def on_signal(
        self,
        signal: int,
        frame: np.ndarray,
        *,
        timestamp: float | None = None,
    ) -> SnapshotEvent | None:
        """
        Observe a new FSM signal and save a snapshot on rising STOP/SLOW edges.

        Returns SnapshotEvent when a JPEG is written, else None.
        """
        kind = self._rising_edge_kind(signal)
        self._prev_signal = signal
        if kind is None:
            return None
        if not self._config.snapshot:
            return None

        ts = time.time() if timestamp is None else timestamp
        path = self._snapshot_path(kind, ts)
        self._write_jpeg(frame, path)
        self._enforce_retention()
        event = SnapshotEvent(
            station_id=self._station_id,
            kind=kind,
            signal=signal,
            path=path,
            timestamp=ts,
        )
        logger.info(
            "snapshot saved station=%s kind=%s path=%s",
            self._station_id,
            kind,
            path,
        )
        return event

    def _rising_edge_kind(self, signal: int) -> SignalKind | None:
        if signal == SIGNAL_STOP and self._prev_signal != SIGNAL_STOP:
            return "stop"
        if (
            self._save_on_slow
            and signal == SIGNAL_SLOW
            and self._prev_signal != SIGNAL_SLOW
        ):
            return "slow"
        return None

    def _snapshot_path(self, kind: SignalKind, timestamp: float) -> Path:
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        stamp = dt.strftime("%Y%m%dT%H%M%S")
        millis = int((timestamp % 1) * 1000)
        event_dir = (
            self._output_dir
            / self._station_id
            / f"{stamp}_{millis:03d}_{kind}"
        )
        return event_dir / "snapshot.jpg"

    def _write_jpeg(self, frame: np.ndarray, path: Path) -> None:
        import cv2

        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError(f"expected BGR image HxWx3, got shape {frame.shape}")
        if frame.dtype != np.uint8:
            raise ValueError(f"expected uint8 frame, got dtype {frame.dtype}")

        path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(path), frame):
            raise OSError(f"failed to write snapshot: {path}")

    def _enforce_retention(self) -> None:
        station_root = self._output_dir / self._station_id
        if not station_root.is_dir():
            return

        event_dirs = sorted(
            (p for p in station_root.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
        )
        excess = len(event_dirs) - self._max_snapshots
        for old_dir in event_dirs[:excess]:
            for child in old_dir.iterdir():
                child.unlink(missing_ok=True)
            old_dir.rmdir()
            logger.debug("retention removed %s", old_dir)
