"""
Strategy phase state dataclasses and constants.
No I/O, no MT5, no GUI dependency.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Phase(str, Enum):
    SCANNING = "SCANNING"
    ARMED_LONG = "ARMED_LONG"
    ARMED_SHORT = "ARMED_SHORT"
    WINDOW_OPEN = "WINDOW_OPEN"
    AWAITING_ENTRY = "AWAITING_ENTRY"
    IN_TRADE = "IN_TRADE"


@dataclass
class PhaseState:
    symbol: str
    phase: Phase = Phase.SCANNING
    pullback_count: int = 0
    window_open: bool = False
    window_expiry_bar: int = 0
    window_breakout_level: Optional[float] = None
    signal_candle_index: int = 0
    signal_bar_time: Optional[str] = None  # ISO string for persistence
    direction: Optional[str] = None  # "LONG" or "SHORT"
    active_ticket: Optional[int] = None  # set when IN_TRADE

    def reset(self) -> None:
        """Return to SCANNING state, clearing all transient fields."""
        self.phase = Phase.SCANNING
        self.pullback_count = 0
        self.window_open = False
        self.window_expiry_bar = 0
        self.window_breakout_level = None
        self.signal_candle_index = 0
        self.signal_bar_time = None
        self.direction = None
        self.active_ticket = None
