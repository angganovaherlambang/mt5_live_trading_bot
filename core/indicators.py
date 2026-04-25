"""
Technical indicator calculations for the MT5 bot.

All functions are pure (no side effects, no MT5/GUI dependency).
Input: a pandas DataFrame with columns [open, high, low, close, tick_volume].
Output: dicts or scalar values — never modifies the input DataFrame.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Optional


def _ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average, matching MT5's default (adjust=False)."""
    return series.ewm(span=period, adjust=False).mean()


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Average True Range over `period` bars."""
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def calculate_indicators(df: pd.DataFrame, config: dict) -> dict:
    """
    Compute all indicators needed by the strategy state machine.

    Returns a dict with scalar values for the most recent completed bar
    and full Series where the state machine needs historical context.

    Keys returned:
        ema_fast, ema_medium, ema_slow, ema_confirm, ema_filter  — pd.Series
        atr        — float (last completed bar, index -2)
        atr_prev   — float (bar before that, index -3)
        atr_series — pd.Series (full ATR history)
        trend      — str: "BULLISH" | "BEARISH" | "NEUTRAL"
        ema_fast_last, ema_slow_last  — float (last completed bar)
    """
    fast_period = int(config.get("ema_fast_length", 18))
    medium_period = int(config.get("ema_medium_length", 18))
    slow_period = int(config.get("ema_slow_length", 24))
    confirm_period = int(config.get("ema_confirm_length", 1))
    filter_period = int(config.get("ema_filter_price_length", 70))
    atr_period = int(config.get("atr_length", 10))

    ema_fast = _ema(df["close"], fast_period)
    ema_medium = _ema(df["close"], medium_period)
    ema_slow = _ema(df["close"], slow_period)
    ema_confirm = _ema(df["close"], confirm_period)
    ema_filter = _ema(df["close"], filter_period)
    atr_series = _atr(df, atr_period)

    # Use index -2 = last *closed* bar (index -1 is the in-progress bar)
    fast_last = ema_fast.iloc[-2]
    slow_last = ema_slow.iloc[-2]
    atr_val = atr_series.iloc[-2]
    atr_prev = atr_series.iloc[-3] if len(atr_series) >= 3 else atr_val

    if fast_last > slow_last:
        trend = "BULLISH"
    elif fast_last < slow_last:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"

    return {
        "ema_fast": ema_fast,
        "ema_medium": ema_medium,
        "ema_slow": ema_slow,
        "ema_confirm": ema_confirm,
        "ema_filter": ema_filter,
        "atr_series": atr_series,
        "atr": atr_val,
        "atr_prev": atr_prev,
        "trend": trend,
        "ema_fast_last": fast_last,
        "ema_slow_last": slow_last,
    }


def detect_ema_crossover_at_index(
    df: pd.DataFrame,
    indicators: dict,
    bar_index: int,
) -> Optional[str]:
    """
    Check if the fast EMA crossed the slow EMA at `bar_index`.

    Returns "LONG" if fast crossed above slow, "SHORT" if fast crossed below slow,
    None if no crossover.

    `bar_index` uses Python negative indexing: -2 = last closed bar.
    """
    fast = indicators["ema_fast"]
    slow = indicators["ema_slow"]
    prev = bar_index - 1  # one bar earlier

    if abs(bar_index) >= len(fast) or abs(prev) >= len(fast):
        return None

    fast_now = fast.iloc[bar_index]
    slow_now = slow.iloc[bar_index]
    fast_prev = fast.iloc[prev]
    slow_prev = slow.iloc[prev]

    if fast_prev <= slow_prev and fast_now > slow_now:
        return "LONG"
    if fast_prev >= slow_prev and fast_now < slow_now:
        return "SHORT"
    return None
