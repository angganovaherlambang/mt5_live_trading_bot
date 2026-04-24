import pytest
from core.config_loader import extract_numeric_value, extract_bool_value, validate_critical_params


class TestExtractNumericValue:
    def test_plain_integer(self):
        assert extract_numeric_value("ema_fast_length = 18") == 18.0

    def test_plain_float(self):
        assert extract_numeric_value("LONG_ATR_MIN_THRESHOLD = 0.000150") == 0.000150

    def test_returns_none_for_missing(self):
        assert extract_numeric_value("some_other_line = abc") is None

    def test_negative_value(self):
        assert extract_numeric_value("LONG_ATR_DECREMENT_MIN_THRESHOLD = -0.000025") == -0.000025


class TestExtractBoolValue:
    def test_true(self):
        assert extract_bool_value("ENABLE_LONG_TRADES = True") is True

    def test_false(self):
        assert extract_bool_value("ENABLE_LONG_TRADES = False") is False

    def test_returns_none_for_missing(self):
        assert extract_bool_value("some_other_line = 123") is None


class TestValidateCriticalParams:
    def test_valid_long_only_config(self, eurusd_config):
        missing = validate_critical_params(eurusd_config)
        assert missing == []

    def test_missing_required_param(self, eurusd_config):
        del eurusd_config["long_atr_sl_multiplier"]
        missing = validate_critical_params(eurusd_config)
        assert "long_atr_sl_multiplier" in missing

    def test_short_params_not_required_when_shorts_disabled(self, eurusd_config):
        # ENABLE_SHORT_TRADES=False means SHORT-specific params are not required
        missing = validate_critical_params(eurusd_config)
        assert missing == []
