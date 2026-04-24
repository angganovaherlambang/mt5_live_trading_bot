"""
Six-layer entry filter stack for the Sunrise Ogle strategy.

All functions are pure: given scalar inputs and a config dict, return bool.
No MT5, GUI, or I/O dependency.

`direction` parameter is "LONG" or "SHORT" throughout.
"""
from __future__ import annotations
from datetime import datetime


def validate_atr_filter(
    atr: float,
    atr_prev: float,
    config: dict,
    direction: str,
) -> bool:
    """Volatility range check + optional increment/decrement check."""
    pfx = direction  # "LONG" or "SHORT"

    if not config.get(f"{pfx}_USE_ATR_FILTER", False):
        return True

    atr_min = config.get(f"{pfx}_ATR_MIN_THRESHOLD", 0.0)
    atr_max = config.get(f"{pfx}_ATR_MAX_THRESHOLD", float("inf"))
    if not (atr_min <= atr <= atr_max):
        return False

    increment = atr - atr_prev

    if config.get(f"{pfx}_USE_ATR_INCREMENT_FILTER", False):
        inc_min = config.get(f"{pfx}_ATR_INCREMENT_MIN_THRESHOLD", 0.0)
        inc_max = config.get(f"{pfx}_ATR_INCREMENT_MAX_THRESHOLD", float("inf"))
        if not (inc_min <= increment <= inc_max):
            return False

    if config.get(f"{pfx}_USE_ATR_DECREMENT_FILTER", False):
        dec_min = config.get(f"{pfx}_ATR_DECREMENT_MIN_THRESHOLD", float("-inf"))
        dec_max = config.get(f"{pfx}_ATR_DECREMENT_MAX_THRESHOLD", 0.0)
        if not (dec_min <= increment <= dec_max):
            return False

    return True


def validate_angle_filter(
    ema_angle_degrees: float,
    config: dict,
    direction: str,
) -> bool:
    """EMA slope angle check."""
    pfx = direction
    if not config.get(f"{pfx}_USE_ANGLE_FILTER", False):
        return True
    min_angle = config.get(f"{pfx}_MIN_ANGLE", 0.0)
    max_angle = config.get(f"{pfx}_MAX_ANGLE", 90.0)
    return min_angle <= ema_angle_degrees <= max_angle


def validate_price_filter(
    price: float,
    ema_filter: float,
    config: dict,
    direction: str,
) -> bool:
    """Price must be on the correct side of the filter EMA."""
    pfx = direction
    if not config.get(f"{pfx}_USE_PRICE_FILTER_EMA", False):
        return True
    if direction == "LONG":
        return price > ema_filter
    return price < ema_filter


def validate_candle_direction(
    prev_open: float,
    prev_close: float,
    config: dict,
    direction: str,
) -> bool:
    """Previous candle must be bullish (LONG) or bearish (SHORT)."""
    pfx = direction
    if not config.get(f"{pfx}_USE_CANDLE_DIRECTION_FILTER", False):
        return True
    if direction == "LONG":
        return prev_close > prev_open
    return prev_close < prev_open


def validate_ema_ordering(
    ema_confirm: float,
    ema_fast: float,
    ema_slow: float,
    config: dict,
    direction: str,
) -> bool:
    """EMAs must be stacked in trend direction."""
    pfx = direction
    if not config.get(f"{pfx}_USE_EMA_ORDER_CONDITION", False):
        return True
    if direction == "LONG":
        return ema_confirm > ema_fast > ema_slow
    return ema_confirm < ema_fast < ema_slow


def validate_time_filter(
    now_utc: datetime,
    config: dict,
    utc_offset: int = 0,
) -> bool:
    """
    Restrict entries to a configured UTC time window.
    utc_offset adjusts broker time to UTC (e.g. +2 means broker is UTC+2).
    """
    if not config.get("USE_TIME_RANGE_FILTER", False):
        return True

    broker_hour = (now_utc.hour + utc_offset) % 24
    broker_minute = now_utc.minute

    start_h = int(config.get("ENTRY_START_HOUR", 0))
    start_m = int(config.get("ENTRY_START_MINUTE", 0))
    end_h = int(config.get("ENTRY_END_HOUR", 23))
    end_m = int(config.get("ENTRY_END_MINUTE", 59))

    current = broker_hour * 60 + broker_minute
    start = start_h * 60 + start_m
    end = end_h * 60 + end_m

    if start <= end:
        return start <= current <= end
    # Window wraps midnight
    return current >= start or current <= end
