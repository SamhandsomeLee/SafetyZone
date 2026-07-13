"""Map runtime signal + fault to PLC INT16 (design §6.3/§6.4, D-008 SSOT)."""

from __future__ import annotations


class SignalAdapter:
    """Bootstrap signal → PLC INT16 mapping; sole SSOT for simulated/real writes."""

    @staticmethod
    def to_plc_int16(signal: int, *, fault: bool = False) -> int:
        """Return INT16 value that would be written to PLC for *signal* and *fault*."""
        if fault:
            return -1
        if signal == 2:
            return 2
        if signal == 1:
            return 1
        return 0
