"""Frame-level intrusion state machine (slow/stop dual channel)."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.zone import ZoneHit

# Signal semantics (design doc §6.3):
#  2 = STOP confirmed
#  1 = SLOW confirmed
#  0 = raw intrusion, not yet confirmed (transition / warning)
# -1 = no target in zone OR fault


@dataclass
class _ChannelState:
    enter_streak: int = 0
    exit_streak: int = 0
    active: bool = False
    raw_present: bool = False


@dataclass
class IntrusionFSM:
    enter_frames: int = 2
    exit_frames: int = 10
    fault: bool = False
    _slow: _ChannelState = field(default_factory=_ChannelState)
    _stop: _ChannelState = field(default_factory=_ChannelState)

    def set_fault(self, fault: bool) -> None:
        self.fault = fault

    def update(self, zone_hit: ZoneHit) -> int:
        """
        Update FSM with per-frame zone judgment for one station.
        zone_hit: 'stop' | 'slow' | None
        """
        if self.fault:
            return -1

        slow_raw = zone_hit in ("slow", "stop")
        stop_raw = zone_hit == "stop"

        self._slow.raw_present = slow_raw
        self._stop.raw_present = stop_raw

        self._advance(self._slow, slow_raw)
        self._advance(self._stop, stop_raw)

        if self._stop.active:
            return 2
        if self._slow.active:
            return 1
        if slow_raw or stop_raw:
            return 0
        return -1

    def _advance(self, ch: _ChannelState, present: bool) -> None:
        if present:
            ch.enter_streak += 1
            ch.exit_streak = 0
            if ch.enter_streak >= self.enter_frames:
                ch.active = True
        else:
            ch.exit_streak += 1
            ch.enter_streak = 0
            if ch.exit_streak >= self.exit_frames:
                ch.active = False

    def reset(self) -> None:
        self.fault = False
        self._slow = _ChannelState()
        self._stop = _ChannelState()
