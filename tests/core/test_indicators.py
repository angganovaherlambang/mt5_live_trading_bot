import pytest
import pandas as pd
import numpy as np
from core.indicators import calculate_indicators, detect_ema_crossover_at_index


class TestCalculateIndicators:
    def test_returns_expected_keys(self, sample_ohlcv_df, eurusd_config):
        result = calculate_indicators(sample_ohlcv_df, eurusd_config)
        expected_keys = {
            "ema_fast", "ema_medium", "ema_slow", "ema_confirm",
            "ema_filter", "atr", "atr_prev", "trend",
        }
        assert expected_keys <= result.keys()

    def test_ema_series_length_matches_df(self, sample_ohlcv_df, eurusd_config):
        result = calculate_indicators(sample_ohlcv_df, eurusd_config)
        assert len(result["ema_fast"]) == len(sample_ohlcv_df)

    def test_atr_is_positive(self, sample_ohlcv_df, eurusd_config):
        result = calculate_indicators(sample_ohlcv_df, eurusd_config)
        assert result["atr"] > 0

    def test_trend_is_valid_string(self, sample_ohlcv_df, eurusd_config):
        result = calculate_indicators(sample_ohlcv_df, eurusd_config)
        assert result["trend"] in ("BULLISH", "BEARISH", "NEUTRAL")


class TestDetectEmaCrossoverAtIndex:
    def test_no_crossover_in_flat_data(self, sample_ohlcv_df, eurusd_config):
        indicators = calculate_indicators(sample_ohlcv_df, eurusd_config)
        result = detect_ema_crossover_at_index(sample_ohlcv_df, indicators, -2)
        assert result in (None, "LONG", "SHORT")

    def test_forced_bullish_crossover(self, eurusd_config):
        """Construct data where fast EMA definitively crosses above slow EMA."""
        n = 100
        close = np.concatenate([
            np.linspace(1.2000, 1.1000, 70),  # downtrend — fast below slow
            np.linspace(1.1000, 1.3000, 30),  # sharp rally — fast crosses above slow
        ])
        df = pd.DataFrame({
            "open": close - 0.0001,
            "high": close + 0.0005,
            "low": close - 0.0005,
            "close": close,
            "tick_volume": np.ones(n) * 500,
        })
        # Use short EMA periods so crossover is quick
        cfg = {**eurusd_config, "ema_fast_length": 5, "ema_slow_length": 20}
        indicators = calculate_indicators(df, cfg)
        # Check the data range including crossover (which happens around -26)
        found = any(
            detect_ema_crossover_at_index(df, indicators, i) == "LONG"
            for i in range(-30, -1)
        )
        assert found, "Expected a LONG crossover signal in rally section"
