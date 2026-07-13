"""Tests for plc.simulate."""

from __future__ import annotations

from plc.simulate import SimulateBackend


def test_simulate_open_write_read_close() -> None:
    backend = SimulateBackend()
    assert not backend.connected
    assert backend.write_int16(1) is False

    backend.open()
    assert backend.connected
    assert backend.write_int16(2) is True
    assert backend.read_int16() == 2
    assert backend.last_written == 2

    backend.close()
    assert not backend.connected
    assert backend.read_int16() is None
