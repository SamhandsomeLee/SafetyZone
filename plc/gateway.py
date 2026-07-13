"""PLC Gateway: backend abstraction and signal → INT16 write path (D-008)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from app.signal_adapter import SignalAdapter
from core.config import PlcConfig

logger = logging.getLogger(__name__)


class PlcBackend(Protocol):
    """Backend contract for INT16 write / optional read-back."""

    @property
    def connected(self) -> bool:
        """Whether the backend session is open."""

    def open(self) -> None:
        """Open backend session (connect or enter simulate mode)."""

    def close(self) -> None:
        """Close backend session."""

    def write_int16(self, value: int) -> bool:
        """Write INT16 to PLC (or simulate). Return True on success."""

    def read_int16(self) -> int | None:
        """Read INT16 for verify; None if unavailable."""


@dataclass(frozen=True)
class PlcWriteResult:
    """Outcome of mapping signal → INT16 and optional backend write."""

    signal: int
    fault: bool
    plc_int16: int
    written: bool
    read_back: int | None = None
    read_back_ok: bool | None = None


def should_use_snap7(config: PlcConfig) -> bool:
    """True when real snap7 path is selected (D-007 / Wave2)."""
    return config.enabled and not config.simulate


def create_backend(config: PlcConfig) -> PlcBackend:
    """Factory: simulate when disabled or simulating; snap7 when enabled + real."""
    if should_use_snap7(config):
        from plc.snap7_backend import Snap7Backend

        return Snap7Backend(config)

    from plc.simulate import SimulateBackend

    return SimulateBackend()


class PlcGateway:
    """Serializes signal writes through a PlcBackend using SignalAdapter mapping."""

    def __init__(self, config: PlcConfig, backend: PlcBackend | None = None) -> None:
        self._config = config
        self._backend = backend if backend is not None else create_backend(config)
        self._opened = False

    @property
    def config(self) -> PlcConfig:
        return self._config

    @property
    def backend(self) -> PlcBackend:
        return self._backend

    @property
    def simulate(self) -> bool:
        return self._config.simulate or not self._config.enabled

    @property
    def connected(self) -> bool:
        return self._opened and self._backend.connected

    def open(self) -> None:
        if self._opened:
            return
        self._backend.open()
        self._opened = True
        logger.info(
            "PLC gateway open simulate=%s enabled=%s connected=%s",
            self.simulate,
            self._config.enabled,
            self._backend.connected,
        )

    def close(self) -> None:
        if not self._opened:
            return
        self._backend.close()
        self._opened = False

    def write_signal(self, signal: int, *, fault: bool = False) -> PlcWriteResult:
        """Map signal via SignalAdapter and write INT16 through backend."""
        plc_int16 = SignalAdapter.to_plc_int16(signal, fault=fault)
        if not self._opened:
            return PlcWriteResult(
                signal=signal,
                fault=fault,
                plc_int16=plc_int16,
                written=False,
            )

        written = self._backend.write_int16(plc_int16)
        read_back = self._backend.read_int16()
        read_back_ok: bool | None = None
        if read_back is not None:
            read_back_ok = read_back == plc_int16

        return PlcWriteResult(
            signal=signal,
            fault=fault,
            plc_int16=plc_int16,
            written=written,
            read_back=read_back,
            read_back_ok=read_back_ok,
        )
