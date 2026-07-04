"""Signal labels and display helpers (new signal semantics vs legacy result_code)."""

from __future__ import annotations

SIGNAL_LABELS: dict[int, tuple[str, str]] = {
    -1: ("SAFE", "#50c850"),
    0: ("WARN", "#00c8ff"),
    1: ("SLOW", "#ffb400"),
    2: ("STOP", "#ff3030"),
}

STOCK_BADGE = "STOCK · 集成测试 · 未过场内验收"


def signal_label(signal: int, *, fault: bool = False) -> str:
    if fault:
        return "FAULT"
    return SIGNAL_LABELS.get(signal, (str(signal), "#ffffff"))[0]


def signal_color_hex(signal: int, *, fault: bool = False) -> str:
    if fault:
        return "#ff6060"
    return SIGNAL_LABELS.get(signal, (str(signal), "#ffffff"))[1]


def plc_sim_value(signal: int, *, fault: bool = False) -> int:
    """Bootstrap PLC simulation INT16 (design doc §6.4 subset)."""
    if fault:
        return -1
    if signal == 2:
        return 2
    if signal == 1:
        return 1
    if signal == 0:
        return 0
    return 0
