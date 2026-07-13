"""Tests for SignalAdapter (signal + fault → PLC INT16, D-008)."""

from __future__ import annotations

import pytest

from app.signal_adapter import SignalAdapter
from app.signal_display import plc_sim_value


@pytest.mark.parametrize(
    ("signal", "fault", "expected"),
    [
        (-1, True, -1),
        (0, True, -1),
        (1, True, -1),
        (2, True, -1),
        (2, False, 2),
        (1, False, 1),
        (0, False, 0),
        (-1, False, 0),
        (99, False, 0),
        (-99, False, 0),
    ],
)
def test_to_plc_int16_mapping(signal: int, fault: bool, expected: int) -> None:
    assert SignalAdapter.to_plc_int16(signal, fault=fault) == expected


def test_matches_plc_sim_value_semantics() -> None:
    """Bootstrap UI helper and Adapter stay aligned until #23 delegates."""
    cases: list[tuple[int, bool]] = [
        (-1, False),
        (-1, True),
        (0, False),
        (0, True),
        (1, False),
        (1, True),
        (2, False),
        (2, True),
        (3, False),
        (3, True),
    ]
    for signal, fault in cases:
        assert SignalAdapter.to_plc_int16(signal, fault=fault) == plc_sim_value(
            signal, fault=fault
        )
