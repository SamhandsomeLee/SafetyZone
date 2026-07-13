"""Tests for plc.snap7_backend (mocked; no real PLC required)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from core.config import PlcConfig
from plc.gateway import create_backend
from plc.snap7_backend import Snap7Backend, _decode_int16, _encode_int16


class _FakeSnap7Client:
    def __init__(self) -> None:
        self._connected = False
        self.written: bytes | None = None
        self.connect_args: tuple[Any, ...] | None = None

    def connect(self, address: str, rack: int, slot: int, tcp_port: int = 102) -> _FakeSnap7Client:
        self.connect_args = (address, rack, slot, tcp_port)
        self._connected = True
        return self

    def get_connected(self) -> bool:
        return self._connected

    def disconnect(self) -> None:
        self._connected = False

    def db_write(self, db_number: int, start: int, data: bytes) -> None:
        assert db_number == 1
        assert start == 0
        self.written = data

    def db_read(self, db_number: int, start: int, size: int) -> bytes:
        assert db_number == 1
        assert start == 0
        assert size == 2
        if self.written is None:
            return b"\x00\x00"
        return self.written


def test_encode_decode_int16_roundtrip() -> None:
    assert _decode_int16(_encode_int16(2)) == 2
    assert _decode_int16(_encode_int16(-1)) == -1


def test_open_skipped_when_simulate_true() -> None:
    fake = _FakeSnap7Client()
    backend = Snap7Backend(
        PlcConfig(enabled=True, simulate=True),
        client_factory=lambda: fake,
    )
    backend.open()
    assert fake.connect_args is None
    assert not backend.connected


def test_open_skipped_when_enabled_false() -> None:
    fake = _FakeSnap7Client()
    backend = Snap7Backend(
        PlcConfig(enabled=False, simulate=False),
        client_factory=lambda: fake,
    )
    backend.open()
    assert fake.connect_args is None
    assert not backend.connected


def test_open_connects_with_config_when_real_path() -> None:
    fake = _FakeSnap7Client()
    backend = Snap7Backend(
        PlcConfig(
            enabled=True,
            simulate=False,
            ip="10.0.0.5",
            rack=1,
            slot=2,
            db_number=1,
            result_offset=0,
        ),
        client_factory=lambda: fake,
    )
    backend.open()
    assert fake.connect_args == ("10.0.0.5", 1, 2, 102)
    assert backend.connected


def test_write_int16_with_readback_ok() -> None:
    fake = _FakeSnap7Client()
    backend = Snap7Backend(
        PlcConfig(enabled=True, simulate=False, verify_readback=True),
        client_factory=lambda: fake,
    )
    backend.open()
    written, read_back, ok = backend.write_int16_with_readback(2)
    assert written is True
    assert read_back == 2
    assert ok is True


def test_write_without_open_returns_false() -> None:
    backend = Snap7Backend(PlcConfig(enabled=True, simulate=False))
    assert backend.write_int16(1) is False
    assert backend.read_int16() is None


def test_create_backend_returns_snap7_when_real_path() -> None:
    backend = create_backend(PlcConfig(enabled=True, simulate=False))
    assert isinstance(backend, Snap7Backend)


def test_create_client_uses_injected_factory() -> None:
    factory = MagicMock(return_value=_FakeSnap7Client())
    backend = Snap7Backend(
        PlcConfig(enabled=True, simulate=False),
        client_factory=factory,
    )
    backend.open()
    factory.assert_called_once()


def test_encode_int16_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="INT16"):
        _encode_int16(40000)
