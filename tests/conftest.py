import pytest
import pandas as pd
import numpy as np


@pytest.fixture
def sample_ohlcv_df():
    """150 bars of fake M5 OHLCV data."""
    n = 150
    np.random.seed(42)
    close = 1.1000 + np.cumsum(np.random.randn(n) * 0.0002)
    high = close + np.random.uniform(0.0001, 0.0005, n)
    low = close - np.random.uniform(0.0001, 0.0005, n)
    open_ = np.clip(close - np.random.randn(n) * 0.0001, low, high)
    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "tick_volume": np.random.randint(100, 1000, n),
        "time": pd.date_range("2026-01-01", periods=n, freq="5min"),
    })


@pytest.fixture
def eurusd_config():
    """Minimal strategy config matching EURUSD strategy file params."""
    return {
        "ema_fast_length": 18,
        "ema_medium_length": 18,
        "ema_slow_length": 24,
        "ema_confirm_length": 1,
        "ema_filter_price_length": 70,
        "atr_length": 10,
        "LONG_USE_ATR_FILTER": True,
        "LONG_ATR_MIN_THRESHOLD": 0.000150,
        "LONG_ATR_MAX_THRESHOLD": 0.000499,
        "LONG_USE_ATR_INCREMENT_FILTER": True,
        "LONG_ATR_INCREMENT_MIN_THRESHOLD": 0.000010,
        "LONG_ATR_INCREMENT_MAX_THRESHOLD": 0.000080,
        "LONG_USE_ATR_DECREMENT_FILTER": False,
        "LONG_USE_ANGLE_FILTER": False,
        "LONG_MIN_ANGLE": 35.0,
        "LONG_MAX_ANGLE": 85.0,
        "LONG_ANGLE_SCALE_FACTOR": 10000.0,
        "LONG_USE_PRICE_FILTER_EMA": True,
        "LONG_USE_CANDLE_DIRECTION_FILTER": False,
        "LONG_USE_EMA_ORDER_CONDITION": False,
        "USE_TIME_RANGE_FILTER": False,
        "ENTRY_START_HOUR": 21,
        "ENTRY_START_MINUTE": 0,
        "ENTRY_END_HOUR": 3,
        "ENTRY_END_MINUTE": 0,
        "LONG_USE_PULLBACK_ENTRY": True,
        "LONG_PULLBACK_MAX_CANDLES": 2,
        "LONG_ENTRY_WINDOW_PERIODS": 1,
        "USE_WINDOW_TIME_OFFSET": False,
        "WINDOW_OFFSET_MULTIPLIER": 1.0,
        "WINDOW_PRICE_OFFSET_MULTIPLIER": 0.01,
        "long_atr_sl_multiplier": 1.5,
        "long_atr_tp_multiplier": 10.0,
        "ENABLE_LONG_TRADES": True,
        "ENABLE_SHORT_TRADES": False,
    }
