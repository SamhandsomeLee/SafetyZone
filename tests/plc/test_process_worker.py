"""Tests for plc.process_worker (multiprocessing skeleton)."""

from __future__ import annotations

from core.config import PlcConfig
from plc.process_worker import PlcProcessGateway, PlcWorkerState


def test_process_gateway_start_stop() -> None:
    gw = PlcProcessGateway(PlcConfig(simulate=True, enabled=False))
    assert not gw.is_running
    gw.start()
    assert gw.is_running
    status = gw.wait_for_status(
        timeout=5.0,
        predicate=lambda s: s.state == PlcWorkerState.RUNNING,
    )
    assert status is not None
    assert status.simulate is True
    assert status.connected is True
    gw.stop()
    assert not gw.is_running


def test_process_gateway_queue_receives_signal() -> None:
    gw = PlcProcessGateway(PlcConfig(simulate=True))
    gw.start()
    gw.wait_for_status(
        timeout=5.0,
        predicate=lambda s: s.state == PlcWorkerState.RUNNING,
    )
    gw.send_signal(2, fault=False)
    status = gw.wait_for_status(
        timeout=5.0,
        predicate=lambda s: s.last_plc_int16 == 2,
    )
    assert status is not None
    assert status.last_signal == 2
    assert status.last_plc_int16 == 2
    assert status.last_fault is False
    gw.stop()
