"""S7 PLC backend via python-snap7 (connect only when enabled + not simulating)."""

from __future__ import annotations

import logging
import struct
from typing import Any

from core.config import PlcConfig
from plc.gateway import should_use_snap7

logger = logging.getLogger(__name__)

_INT16_SIZE = 2


def _clamp_int16(value: int) -> int:
    if value < -32768 or value > 32767:
        raise ValueError(f"INT16 out of range: {value}")
    return value


def _encode_int16(value: int) -> bytes:
    return struct.pack(">h", _clamp_int16(value))


def _decode_int16(data: bytes) -> int:
    if len(data) < _INT16_SIZE:
        raise ValueError("buffer too short for INT16")
    return struct.unpack(">h", data[:_INT16_SIZE])[0]


class Snap7Backend:
    """Lazy snap7 client; connects only when config selects real PLC path."""

    def __init__(self, config: PlcConfig, client_factory: Any | None = None) -> None:
        self._config = config
        self._client_factory = client_factory
        self._client: Any | None = None

    @staticmethod
    def is_snap7_available() -> bool:
        try:
            import snap7  # noqa: F401

            return True
        except ImportError:
            return False

    @property
    def connected(self) -> bool:
        if self._client is None:
            return False
        try:
            return bool(self._client.get_connected())
        except Exception:
            return False

    def open(self) -> None:
        if not should_use_snap7(self._config):
            logger.debug(
                "Snap7Backend skipped connect enabled=%s simulate=%s",
                self._config.enabled,
                self._config.simulate,
            )
            return
        if self._client is not None and self.connected:
            return

        client = self._create_client()
        client.connect(self._config.ip, self._config.rack, self._config.slot)
        self._client = client
        logger.info(
            "Snap7 connected ip=%s rack=%s slot=%s db=%s offset=%s",
            self._config.ip,
            self._config.rack,
            self._config.slot,
            self._config.db_number,
            self._config.result_offset,
        )

    def close(self) -> None:
        if self._client is None:
            return
        try:
            if self.connected:
                self._client.disconnect()
        except Exception:
            logger.exception("Snap7 disconnect failed")
        finally:
            self._client = None

    def write_int16(self, value: int) -> bool:
        if self._client is None or not self.connected:
            return False
        payload = _encode_int16(value)
        self._client.db_write(
            self._config.db_number,
            self._config.result_offset,
            payload,
        )
        return True

    def read_int16(self) -> int | None:
        if self._client is None or not self.connected:
            return None
        data = self._client.db_read(
            self._config.db_number,
            self._config.result_offset,
            _INT16_SIZE,
        )
        return _decode_int16(data)

    def write_int16_with_readback(self, value: int) -> tuple[bool, int | None, bool]:
        """Write INT16 then read back for verification (design §6.4)."""
        written = self.write_int16(value)
        if not written:
            return False, None, False
        if not self._config.verify_readback:
            return True, None, True
        read_back = self.read_int16()
        if read_back is None:
            return True, None, False
        return True, read_back, read_back == _clamp_int16(value)

    def _create_client(self) -> Any:
        if self._client_factory is not None:
            return self._client_factory()
        import snap7

        return snap7.client.Client()
