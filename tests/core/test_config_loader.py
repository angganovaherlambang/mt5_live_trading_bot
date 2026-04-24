import pytest
from core.config_loader import (
    extract_numeric_value,
    extract_bool_value,
    validate_critical_params,
    parse_strategy_config,
    load_all_configs,
)


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


class TestParseStrategyConfig:
    def test_parses_eurusd_strategy_file(self):
        """Parse the real EURUSD strategy file and verify key params are extracted."""
        from pathlib import Path
        path = Path("strategies/sunrise_ogle_eurusd.py")
        if not path.exists():
            pytest.skip("Strategy file not found")
        config = parse_strategy_config(path)
        assert config.get("ENABLE_LONG_TRADES") is True
        assert "long_atr_sl_multiplier" in config
        assert "ema_fast_length" in config
        assert "LONG_ATR_MIN_THRESHOLD" in config
        assert isinstance(config["ema_fast_length"], float)

    def test_missing_file_returns_empty_dict(self, tmp_path):
        config = parse_strategy_config(tmp_path / "nonexistent.py")
        assert config == {}

    def test_parses_inline_comment_lines(self, tmp_path):
        """Values with inline comments must be parsed correctly."""
        strategy_file = tmp_path / "test_strategy.py"
        strategy_file.write_text(
            "ENABLE_LONG_TRADES = True  # enable longs\n"
            "LONG_ATR_MIN_THRESHOLD = 0.000150  # min ATR\n"
            "ema_fast_length = 18  # fast EMA\n"
        )
        config = parse_strategy_config(strategy_file)
        assert config["ENABLE_LONG_TRADES"] is True
        assert config["LONG_ATR_MIN_THRESHOLD"] == 0.000150
        assert config["ema_fast_length"] == 18.0


class TestLoadAllConfigs:
    def test_loads_eurusd_config(self):
        from pathlib import Path
        strategies_dir = Path("strategies")
        if not strategies_dir.exists():
            pytest.skip("strategies/ dir not found")
        configs = load_all_configs(strategies_dir, ["EURUSD"])
        assert "EURUSD" in configs
        # Should have valid config (non-empty), not garbage
        assert configs["EURUSD"].get("ENABLE_LONG_TRADES") is True

    def test_missing_symbol_returns_empty_dict(self, tmp_path):
        configs = load_all_configs(tmp_path, ["FAKESYM"])
        assert configs["FAKESYM"] == {}
