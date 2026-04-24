import pytest
from datetime import datetime, timezone
from core.filters import (
    validate_atr_filter,
    validate_angle_filter,
    validate_price_filter,
    validate_candle_direction,
    validate_ema_ordering,
    validate_time_filter,
)


class TestAtrFilter:
    def test_passes_within_range(self, eurusd_config):
        assert validate_atr_filter(0.000200, 0.000160, eurusd_config, "LONG") is True

    def test_fails_below_min(self, eurusd_config):
        assert validate_atr_filter(0.000050, 0.000040, eurusd_config, "LONG") is False

    def test_fails_above_max(self, eurusd_config):
        assert validate_atr_filter(0.001000, 0.000900, eurusd_config, "LONG") is False

    def test_passes_when_filter_disabled(self, eurusd_config):
        cfg = {**eurusd_config, "LONG_USE_ATR_FILTER": False}
        assert validate_atr_filter(0.000010, 0.000009, cfg, "LONG") is True

    def test_increment_filter_blocks_out_of_range(self, eurusd_config):
        # increment = 0.000200 - 0.000160 = 0.000040, below LONG_ATR_INCREMENT_MIN=0.000050
        assert validate_atr_filter(0.000200, 0.000160, eurusd_config, "LONG") is True
        # increment = 0.000155 - 0.000150 = 0.000005, below min → fail
        assert validate_atr_filter(0.000155, 0.000150, eurusd_config, "LONG") is False


class TestAngleFilter:
    def test_passes_when_disabled(self, eurusd_config):
        cfg = {**eurusd_config, "LONG_USE_ANGLE_FILTER": False}
        assert validate_angle_filter(10.0, cfg, "LONG") is True

    def test_passes_in_range(self, eurusd_config):
        cfg = {**eurusd_config, "LONG_USE_ANGLE_FILTER": True}
        assert validate_angle_filter(50.0, cfg, "LONG") is True

    def test_fails_below_min(self, eurusd_config):
        cfg = {**eurusd_config, "LONG_USE_ANGLE_FILTER": True}
        assert validate_angle_filter(20.0, cfg, "LONG") is False


class TestPriceFilter:
    def test_passes_price_above_filter_ema_for_long(self, eurusd_config):
        assert validate_price_filter(price=1.1050, ema_filter=1.1000, config=eurusd_config, direction="LONG") is True

    def test_fails_price_below_filter_ema_for_long(self, eurusd_config):
        assert validate_price_filter(price=1.0950, ema_filter=1.1000, config=eurusd_config, direction="LONG") is False

    def test_passes_when_disabled(self, eurusd_config):
        cfg = {**eurusd_config, "LONG_USE_PRICE_FILTER_EMA": False}
        assert validate_price_filter(price=1.0950, ema_filter=1.1000, config=cfg, direction="LONG") is True


class TestCandleDirection:
    def test_passes_bullish_candle_for_long_when_disabled(self, eurusd_config):
        cfg = {**eurusd_config, "LONG_USE_CANDLE_DIRECTION_FILTER": False}
        assert validate_candle_direction(prev_open=1.10, prev_close=1.09, config=cfg, direction="LONG") is True

    def test_requires_bullish_candle_for_long_when_enabled(self, eurusd_config):
        cfg = {**eurusd_config, "LONG_USE_CANDLE_DIRECTION_FILTER": True}
        assert validate_candle_direction(prev_open=1.09, prev_close=1.10, config=cfg, direction="LONG") is True
        assert validate_candle_direction(prev_open=1.10, prev_close=1.09, config=cfg, direction="LONG") is False


class TestEmaOrdering:
    def test_passes_correct_long_stack(self, eurusd_config):
        cfg = {**eurusd_config, "LONG_USE_EMA_ORDER_CONDITION": True}
        assert validate_ema_ordering(
            ema_confirm=1.105, ema_fast=1.104, ema_slow=1.103,
            config=cfg, direction="LONG"
        ) is True

    def test_fails_wrong_long_stack(self, eurusd_config):
        cfg = {**eurusd_config, "LONG_USE_EMA_ORDER_CONDITION": True}
        assert validate_ema_ordering(
            ema_confirm=1.103, ema_fast=1.104, ema_slow=1.105,
            config=cfg, direction="LONG"
        ) is False

    def test_passes_when_disabled(self, eurusd_config):
        cfg = {**eurusd_config, "LONG_USE_EMA_ORDER_CONDITION": False}
        assert validate_ema_ordering(
            ema_confirm=1.103, ema_fast=1.104, ema_slow=1.105,
            config=cfg, direction="LONG"
        ) is True


class TestTimeFilter:
    def test_passes_when_disabled(self, eurusd_config):
        cfg = {**eurusd_config, "USE_TIME_RANGE_FILTER": False}
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        assert validate_time_filter(now, cfg, utc_offset=0) is True

    def test_passes_within_window(self, eurusd_config):
        cfg = {**eurusd_config, "USE_TIME_RANGE_FILTER": True,
               "ENTRY_START_HOUR": 21, "ENTRY_START_MINUTE": 0,
               "ENTRY_END_HOUR": 3, "ENTRY_END_MINUTE": 0}
        now = datetime(2026, 1, 1, 22, 30, tzinfo=timezone.utc)
        assert validate_time_filter(now, cfg, utc_offset=0) is True

    def test_fails_outside_window(self, eurusd_config):
        cfg = {**eurusd_config, "USE_TIME_RANGE_FILTER": True,
               "ENTRY_START_HOUR": 21, "ENTRY_START_MINUTE": 0,
               "ENTRY_END_HOUR": 3, "ENTRY_END_MINUTE": 0}
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        assert validate_time_filter(now, cfg, utc_offset=0) is False
