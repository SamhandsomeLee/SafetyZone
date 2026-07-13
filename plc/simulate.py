"""In-process PLC simulation backend (no snap7)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SimulateBackend:
    """Stores last written INT16 in memory; never touches snap7."""

    def __init__(self) -> None:
        self._open = False
        self._last_written: int | None = None

    @property
    def connected(self) -> bool:
        return self._open

    @property
    def last_written(self) -> int | None:
        return self._last_written

    def open(self) -> None:
        self._open = True
        logger.debug("SimulateBackend opened")

    def close(self) -> None:
        self._open = False
        logger.debug("SimulateBackend closed")

    def write_int16(self, value: int) -> bool:
        if not self._open:
            return False
        self._last_written = int(value)
        return True

    def read_int16(self) -> int | None:
        if not self._open:
            return None
        return self._last_written
