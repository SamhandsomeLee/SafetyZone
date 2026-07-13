"""Tests for plc.gateway and SignalAdapter alignment."""

from __future__ import annotations

import pytest

from app.signal_adapter import SignalAdapter
from core.config import PlcConfig
from plc.gateway import PlcGateway, create_backend, should_use_snap7
from plc.simulate import SimulateBackend


def test_should_use_snap7_matrix() -> None:
    assert should_use_snap7(PlcConfig(enabled=False, simulate=True)) is False
    assert should_use_snap7(PlcConfig(enabled=True, simulate=True)) is False
    assert should_use_snap7(PlcConfig(enabled=False, simulate=False)) is False
    assert should_use_snap7(PlcConfig(enabled=True, simulate=False)) is True


def test_create_backend_defaults_to_simulate() -> None:
    backend = create_backend(PlcConfig())
    assert isinstance(backend, SimulateBackend)


def test_create_backend_uses_snap7_when_enabled_and_not_simulating() -> None:
    from plc.snap7_backend import Snap7Backend

    backend = create_backend(PlcConfig(enabled=True, simulate=False))
    assert isinstance(backend, Snap7Backend)


@pytest.mark.parametrize(
    ("signal", "fault", "expected"),
    [
        (2, False, 2),
        (1, False, 1),
        (0, False, 0),
        (-1, False, 0),
        (0, True, -1),
    ],
)
def test_gateway_write_signal_uses_signal_adapter(
    signal: int, fault: bool, expected: int
) -> None:
    gateway = PlcGateway(PlcConfig(simulate=True), backend=SimulateBackend())
    gateway.open()
    result = gateway.write_signal(signal, fault=fault)
    assert result.plc_int16 == expected
    assert result.plc_int16 == SignalAdapter.to_plc_int16(signal, fault=fault)
    assert result.written is True
    assert result.read_back == expected
    assert result.read_back_ok is True
    gateway.close()


def test_gateway_write_without_open_not_written() -> None:
    gateway = PlcGateway(PlcConfig(simulate=True), backend=SimulateBackend())
    result = gateway.write_signal(2, fault=False)
    assert result.plc_int16 == 2
    assert result.written is False
