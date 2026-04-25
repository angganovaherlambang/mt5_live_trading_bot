"""
4-phase strategy state machine: SCANNING → ARMED → WINDOW_OPEN → AWAITING_ENTRY.

All functions take a PhaseState + market data and return a (possibly mutated) PhaseState.
No MT5, GUI, or I/O dependency.

CONTRACT: All transition functions mutate the PhaseState object in-place. The caller owns
the object and must ensure no concurrent access. The monitor loop processes symbols
sequentially — one symbol at a time — to satisfy this contract.
"""
from __future__ import annotations
import logging
from typing import Optional

import pandas as pd

from core.state import PhaseState, Phase
from core.indicators import detect_ema_crossover_at_index
from core.filters import (
    validate_atr_filter,
    validate_angle_filter,
    validate_price_filter,
    validate_candle_direction,
    validate_ema_ordering,
    validate_time_filter,
)

logger = logging.getLogger(__name__)


def _all_entry_filters_pass(
    indicators: dict,
    df: pd.DataFrame,
    config: dict,
    direction: str,
    bar_index: int,
    now_utc=None,
    utc_offset: int = 0,
) -> bool:
    """Run the full filter cascade for one direction. Returns True only if all enabled filters pass."""
    from datetime import datetime, timezone
    if now_utc is None:
        now_utc = datetime.now(tz=timezone.utc)

    atr = indicators["atr"]
    atr_prev = indicators["atr_prev"]
    ema_fast_val = indicators["ema_fast"].iloc[bar_index]
    ema_slow_val = indicators["ema_slow"].iloc[bar_index]
    ema_confirm_val = indicators["ema_confirm"].iloc[bar_index]
    ema_filter_val = indicators["ema_filter"].iloc[bar_index]
    price = df["close"].iloc[bar_index]
    prev_open = df["open"].iloc[bar_index - 1]
    prev_close = df["close"].iloc[bar_index - 1]

    # EMA slope angle (simplified: use ema_fast slope over 5 bars)
    ema_fast_series = indicators["ema_fast"]
    if len(ema_fast_series) >= abs(bar_index) + 5:
        slope = (ema_fast_series.iloc[bar_index] - ema_fast_series.iloc[bar_index - 5])
        scale = config.get(f"{direction}_ANGLE_SCALE_FACTOR", 10000.0)
        angle = abs(slope * scale)
    else:
        angle = 0.0

    checks = [
        validate_atr_filter(atr, atr_prev, config, direction),
        validate_angle_filter(angle, config, direction),
        validate_price_filter(price, ema_filter_val, config, direction),
        validate_candle_direction(prev_open, prev_close, config, direction),
        validate_ema_ordering(ema_confirm_val, ema_fast_val, ema_slow_val, config, direction),
        validate_time_filter(now_utc, config, utc_offset),
    ]
    return all(checks)


def transition_scanning(
    state: PhaseState,
    df: pd.DataFrame,
    indicators: dict,
    config: dict,
    bar_index: int = -2,
) -> PhaseState:
    """
    SCANNING phase: check for EMA crossover at bar_index.
    If found and filters pass → ARMED_LONG or ARMED_SHORT.
    """
    if state.phase != Phase.SCANNING:
        return state

    for direction in ("LONG", "SHORT"):
        if not config.get(f"ENABLE_{direction}_TRADES", False):
            continue
        crossover = detect_ema_crossover_at_index(df, indicators, bar_index)
        if crossover != direction:
            continue
        if not _all_entry_filters_pass(indicators, df, config, direction, bar_index):
            logger.debug("%s: %s crossover blocked by filters", state.symbol, direction)
            continue
        state.phase = Phase.ARMED_LONG if direction == "LONG" else Phase.ARMED_SHORT
        state.direction = direction
        state.signal_candle_index = bar_index
        state.pullback_count = 0
        logger.info("%s: SCANNING → %s (crossover at bar %d)", state.symbol, state.phase.value, bar_index)
        return state

    return state


def transition_armed(
    state: PhaseState,
    df: pd.DataFrame,
    indicators: dict,
    config: dict,
    bar_index: int = -2,
) -> PhaseState:
    """
    ARMED phase: wait for pullback candles, then open the entry window.
    If pullback_max_candles exceeded without pullback → reset to SCANNING.
    """
    if state.phase not in (Phase.ARMED_LONG, Phase.ARMED_SHORT):
        return state

    direction = state.direction
    max_pullback = int(config.get(f"{direction}_PULLBACK_MAX_CANDLES", 2))
    use_pullback = config.get(f"{direction}_USE_PULLBACK_ENTRY", True)

    if not use_pullback:
        # No pullback required: open window immediately
        state.phase = Phase.WINDOW_OPEN
        state.window_open = True
        state.window_expiry_bar = bar_index - int(config.get(f"{direction}_ENTRY_WINDOW_PERIODS", 1))
        price = df["close"].iloc[bar_index]
        atr = indicators["atr"]
        offset = config.get("WINDOW_PRICE_OFFSET_MULTIPLIER", 0.01) * atr
        state.window_breakout_level = price + offset if direction == "LONG" else price - offset
        logger.info("%s: %s → WINDOW_OPEN (no-pullback)", state.symbol, state.phase.value)
        return state

    state.pullback_count += 1

    if state.pullback_count > max_pullback:
        logger.info("%s: Pullback expired after %d candles, resetting", state.symbol, state.pullback_count)
        state.reset()
        return state

    # Check if this bar is a valid pullback candle
    prev_close = df["close"].iloc[bar_index]
    prev_open = df["open"].iloc[bar_index]
    is_pullback = (
        (direction == "LONG" and prev_close < prev_open) or
        (direction == "SHORT" and prev_close > prev_open)
    )
    if is_pullback:
        state.phase = Phase.WINDOW_OPEN
        state.window_open = True
        window_periods = int(config.get(f"{direction}_ENTRY_WINDOW_PERIODS", 1))
        state.window_expiry_bar = bar_index - window_periods
        atr = indicators["atr"]
        offset = config.get("WINDOW_PRICE_OFFSET_MULTIPLIER", 0.01) * atr
        price = df["close"].iloc[bar_index]
        state.window_breakout_level = price + offset if direction == "LONG" else price - offset
        logger.info("%s: ARMED → WINDOW_OPEN after %d pullback candles", state.symbol, state.pullback_count)

    return state


def transition_window_open(
    state: PhaseState,
    df: pd.DataFrame,
    indicators: dict,
    config: dict,
    bar_index: int = -2,
) -> PhaseState:
    """
    WINDOW_OPEN phase: monitor for price breakout above/below window_breakout_level.
    Window expiry resets to SCANNING.
    """
    if state.phase != Phase.WINDOW_OPEN:
        return state

    if bar_index <= state.window_expiry_bar:
        logger.info("%s: Window expired, resetting to SCANNING", state.symbol)
        state.reset()
        return state

    price = df["close"].iloc[bar_index]
    level = state.window_breakout_level

    if level is None:
        state.reset()
        return state

    if state.direction == "LONG" and price > level:
        state.phase = Phase.AWAITING_ENTRY
        logger.info("%s: WINDOW_OPEN → AWAITING_ENTRY (breakout %.5f > %.5f)", state.symbol, price, level)
    elif state.direction == "SHORT" and price < level:
        state.phase = Phase.AWAITING_ENTRY
        logger.info("%s: WINDOW_OPEN → AWAITING_ENTRY (breakout %.5f < %.5f)", state.symbol, price, level)

    return state


def check_global_invalidation(state: PhaseState, crossover_direction: Optional[str]) -> bool:
    """
    Return True if a counter-trend crossover invalidates the current ARMED/WINDOW_OPEN state.
    SCANNING states are never invalidated.
    """
    if state.phase == Phase.SCANNING:
        return False
    if crossover_direction is None:
        return False
    return crossover_direction != state.direction


def advance_state(
    state: PhaseState,
    df: pd.DataFrame,
    indicators: dict,
    config: dict,
    bar_index: int = -2,
) -> PhaseState:
    """
    Top-level state machine tick. Call once per closed candle per symbol.
    Returns the (possibly updated) PhaseState.
    Mutates state in place. Not thread-safe for concurrent calls on the same state object.
    """
    # Check global invalidation first
    crossover = detect_ema_crossover_at_index(df, indicators, bar_index)
    if check_global_invalidation(state, crossover):
        logger.info("%s: Global invalidation by %s crossover, resetting", state.symbol, crossover)
        state.reset()
        return state

    if state.phase == Phase.SCANNING:
        return transition_scanning(state, df, indicators, config, bar_index)
    if state.phase in (Phase.ARMED_LONG, Phase.ARMED_SHORT):
        return transition_armed(state, df, indicators, config, bar_index)
    if state.phase == Phase.WINDOW_OPEN:
        return transition_window_open(state, df, indicators, config, bar_index)
    # AWAITING_ENTRY: order placement handled by monitor loop, not state machine
    return state
