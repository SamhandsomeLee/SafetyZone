"""PLC Gateway worker process: queue IPC, isolated from UI / inference threads."""

from __future__ import annotations

import logging
import multiprocessing as mp
import queue
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from core.config import PlcConfig

logger = logging.getLogger(__name__)

_SHUTDOWN = "__shutdown__"
_WRITE_SIGNAL = "write_signal"


class PlcWorkerState(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass(frozen=True)
class PlcWorkerStatus:
    state: PlcWorkerState
    simulate: bool
    enabled: bool
    connected: bool
    last_plc_int16: int | None = None
    last_signal: int | None = None
    last_fault: bool = False
    error: str | None = None


def _worker_main(
    config_dict: dict[str, Any],
    cmd_q: mp.Queue,
    status_q: mp.Queue,
) -> None:
    """Target for child process: consume signal commands, drive PlcGateway."""
    from plc.gateway import PlcGateway

    config = PlcConfig(**config_dict)
    gateway = PlcGateway(config)

    def publish(
        state: PlcWorkerState,
        *,
        last_plc_int16: int | None = None,
        last_signal: int | None = None,
        last_fault: bool = False,
        error: str | None = None,
    ) -> None:
        status_q.put(
            PlcWorkerStatus(
                state=state,
                simulate=gateway.simulate,
                enabled=config.enabled,
                connected=gateway.connected,
                last_plc_int16=last_plc_int16,
                last_signal=last_signal,
                last_fault=last_fault,
                error=error,
            )
        )

    try:
        gateway.open()
        publish(PlcWorkerState.RUNNING)
    except Exception as exc:
        logger.exception("PLC worker failed to open gateway")
        publish(PlcWorkerState.ERROR, error=str(exc))
        return

    try:
        while True:
            try:
                msg = cmd_q.get(timeout=0.2)
            except queue.Empty:
                continue

            if msg == _SHUTDOWN:
                break

            if not isinstance(msg, dict) or msg.get("op") != _WRITE_SIGNAL:
                continue

            signal = int(msg["signal"])
            fault = bool(msg.get("fault", False))
            try:
                result = gateway.write_signal(signal, fault=fault)
                publish(
                    PlcWorkerState.RUNNING,
                    last_plc_int16=result.plc_int16,
                    last_signal=signal,
                    last_fault=fault,
                )
            except Exception as exc:
                logger.exception("PLC worker write failed")
                publish(
                    PlcWorkerState.ERROR,
                    last_signal=signal,
                    last_fault=fault,
                    error=str(exc),
                )
    finally:
        gateway.close()
        publish(PlcWorkerState.STOPPED)


class PlcProcessGateway:
    """Parent-side handle: start/stop worker and enqueue signal writes."""

    def __init__(self, config: PlcConfig) -> None:
        self._config = config
        self._ctx = mp.get_context("spawn")
        self._cmd_q: mp.Queue | None = None
        self._status_q: mp.Queue | None = None
        self._process: mp.Process | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._cmd_q = self._ctx.Queue()
        self._status_q = self._ctx.Queue()
        self._process = self._ctx.Process(
            target=_worker_main,
            args=(asdict(self._config), self._cmd_q, self._status_q),
            name="plc-gateway",
            daemon=True,
        )
        self._process.start()

    def stop(self, timeout: float = 5.0) -> None:
        if not self.is_running or self._cmd_q is None:
            self._process = None
            return
        self._cmd_q.put(_SHUTDOWN)
        if self._process is not None:
            self._process.join(timeout=timeout)
            if self._process.is_alive():
                logger.warning("PLC worker did not exit within %.1fs; terminating", timeout)
                self._process.terminate()
                self._process.join(timeout=1.0)
        self._process = None
        self._cmd_q = None
        self._status_q = None

    def send_signal(self, signal: int, *, fault: bool = False) -> None:
        if not self.is_running or self._cmd_q is None:
            raise RuntimeError("PLC worker is not running")
        self._cmd_q.put(
            {
                "op": _WRITE_SIGNAL,
                "signal": signal,
                "fault": fault,
            }
        )

    def poll_status(self) -> PlcWorkerStatus | None:
        if self._status_q is None:
            return None
        latest: PlcWorkerStatus | None = None
        while True:
            try:
                latest = self._status_q.get_nowait()
            except queue.Empty:
                break
        return latest

    def wait_for_status(
        self,
        *,
        timeout: float = 5.0,
        predicate: Any | None = None,
    ) -> PlcWorkerStatus | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.poll_status()
            if status is not None:
                if predicate is None or predicate(status):
                    return status
            if not self.is_running:
                return self.poll_status()
            time.sleep(0.05)
        return self.poll_status()
