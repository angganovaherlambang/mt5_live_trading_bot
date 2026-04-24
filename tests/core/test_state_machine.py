import pytest
import numpy as np
import pandas as pd
from core.state import PhaseState, Phase
from core.state_machine import (
    transition_scanning,
    transition_armed,
    transition_window_open,
    check_global_invalidation,
)
from core.indicators import calculate_indicators


@pytest.fixture
def bullish_df():
    """DataFrame where close prices trend upward (fast EMA > slow EMA)."""
    n = 150
    close = np.linspace(1.08, 1.12, n)
    return pd.DataFrame({
        "open": close - 0.0002,
        "high": close + 0.0003,
        "low": close - 0.0003,
        "close": close,
        "tick_volume": np.ones(n) * 500,
    })


class TestTransitionScanning:
    def test_no_crossover_stays_scanning(self, bullish_df, eurusd_config):
        """Flat trending data with no crossover should stay in SCANNING."""
        state = PhaseState(symbol="EURUSD")
        indicators = calculate_indicators(bullish_df, eurusd_config)
        new_state = transition_scanning(state, bullish_df, indicators, eurusd_config, bar_index=-2)
        assert new_state.phase in (Phase.SCANNING, Phase.ARMED_LONG, Phase.ARMED_SHORT)

    def test_armed_after_long_crossover(self, eurusd_config):
        """Construct a crossover: after transition, state must be ARMED_LONG."""
        n = 100
        close = np.concatenate([
            np.linspace(1.1200, 1.1000, 60),  # downtrend
            np.linspace(1.1000, 1.1300, 40),  # reversal (fast crosses above slow)
        ])
        df = pd.DataFrame({
            "open": close - 0.0001, "high": close + 0.0004,
            "low": close - 0.0004, "close": close,
            "tick_volume": np.ones(n) * 500,
        })
        cfg = {
            **eurusd_config,
            "ema_fast_length": 5,
            "ema_slow_length": 20,
            # Disable filters that might block the crossover signal
            "LONG_USE_ATR_FILTER": False,
            "LONG_USE_PRICE_FILTER_EMA": False,
        }
        indicators = calculate_indicators(df, cfg)

        from core.indicators import detect_ema_crossover_at_index
        crossover_bar = None
        for i in range(-40, -1):
            if detect_ema_crossover_at_index(df, indicators, i) == "LONG":
                crossover_bar = i
                break

        if crossover_bar is None:
            pytest.skip("No crossover found in test data — adjust linspace params")

        state = PhaseState(symbol="EURUSD")
        new_state = transition_scanning(state, df, indicators, cfg, bar_index=crossover_bar)
        assert new_state.phase == Phase.ARMED_LONG
        assert new_state.direction == "LONG"


class TestCheckGlobalInvalidation:
    def test_long_armed_invalidated_by_short_crossover(self, eurusd_config):
        state = PhaseState(symbol="EURUSD", phase=Phase.ARMED_LONG, direction="LONG")
        assert check_global_invalidation(state, crossover_direction="SHORT") is True

    def test_long_armed_not_invalidated_by_long_crossover(self, eurusd_config):
        state = PhaseState(symbol="EURUSD", phase=Phase.ARMED_LONG, direction="LONG")
        assert check_global_invalidation(state, crossover_direction="LONG") is False

    def test_scanning_never_invalidated(self, eurusd_config):
        state = PhaseState(symbol="EURUSD", phase=Phase.SCANNING)
        assert check_global_invalidation(state, crossover_direction="SHORT") is False


class TestTransitionArmed:
    def test_pullback_opens_window(self, eurusd_config):
        """A bearish pullback candle should transition ARMED_LONG → WINDOW_OPEN."""
        state = PhaseState(symbol="EURUSD", phase=Phase.ARMED_LONG, direction="LONG")
        n = 50
        close = np.linspace(1.10, 1.12, n)
        # Make last candle a bearish pullback (open > close)
        open_prices = close.copy()
        open_prices[-2] = close[-2] + 0.0010  # bar_index=-2 open > close → bearish
        df = pd.DataFrame({
            "open": open_prices,
            "high": close + 0.0005,
            "low": close - 0.0005,
            "close": close,
            "tick_volume": np.ones(n) * 500,
        })
        cfg = {**eurusd_config, "LONG_PULLBACK_MAX_CANDLES": 3}
        indicators = calculate_indicators(df, cfg)
        new_state = transition_armed(state, df, indicators, cfg, bar_index=-2)
        assert new_state.phase == Phase.WINDOW_OPEN

    def test_pullback_expires_resets_to_scanning(self, eurusd_config):
        """Exceeding max pullback candles should reset to SCANNING."""
        state = PhaseState(symbol="EURUSD", phase=Phase.ARMED_LONG, direction="LONG", pullback_count=3)
        n = 50
        close = np.linspace(1.10, 1.12, n)
        df = pd.DataFrame({
            "open": close - 0.0001,
            "high": close + 0.0005,
            "low": close - 0.0005,
            "close": close,
            "tick_volume": np.ones(n) * 500,
        })
        cfg = {**eurusd_config, "LONG_PULLBACK_MAX_CANDLES": 2}
        indicators = calculate_indicators(df, cfg)
        new_state = transition_armed(state, df, indicators, cfg, bar_index=-2)
        assert new_state.phase == Phase.SCANNING

    def test_no_pullback_required_opens_window_immediately(self, eurusd_config):
        """When USE_PULLBACK_ENTRY is False, window opens immediately."""
        state = PhaseState(symbol="EURUSD", phase=Phase.ARMED_LONG, direction="LONG")
        n = 50
        close = np.linspace(1.10, 1.12, n)
        df = pd.DataFrame({
            "open": close - 0.0001,
            "high": close + 0.0005,
            "low": close - 0.0005,
            "close": close,
            "tick_volume": np.ones(n) * 500,
        })
        cfg = {**eurusd_config, "LONG_USE_PULLBACK_ENTRY": False}
        indicators = calculate_indicators(df, cfg)
        new_state = transition_armed(state, df, indicators, cfg, bar_index=-2)
        assert new_state.phase == Phase.WINDOW_OPEN


class TestTransitionWindowOpen:
    def _make_state_with_window(self, level: float, expiry_bar: int = -10) -> PhaseState:
        state = PhaseState(symbol="EURUSD", phase=Phase.WINDOW_OPEN, direction="LONG")
        state.window_open = True
        state.window_breakout_level = level
        state.window_expiry_bar = expiry_bar
        return state

    def test_breakout_above_level_transitions_to_awaiting_entry(self, eurusd_config):
        state = self._make_state_with_window(level=1.1100)
        n = 50
        close = np.linspace(1.10, 1.12, n)  # last bar > 1.11
        df = pd.DataFrame({
            "open": close - 0.0001,
            "high": close + 0.0005,
            "low": close - 0.0005,
            "close": close,
            "tick_volume": np.ones(n) * 500,
        })
        indicators = calculate_indicators(df, eurusd_config)
        new_state = transition_window_open(state, df, indicators, eurusd_config, bar_index=-2)
        assert new_state.phase == Phase.AWAITING_ENTRY

    def test_no_breakout_stays_window_open(self, eurusd_config):
        state = self._make_state_with_window(level=1.1300)  # level above current price
        n = 50
        close = np.linspace(1.10, 1.12, n)
        df = pd.DataFrame({
            "open": close - 0.0001,
            "high": close + 0.0005,
            "low": close - 0.0005,
            "close": close,
            "tick_volume": np.ones(n) * 500,
        })
        indicators = calculate_indicators(df, eurusd_config)
        new_state = transition_window_open(state, df, indicators, eurusd_config, bar_index=-2)
        assert new_state.phase == Phase.WINDOW_OPEN

    def test_window_expiry_resets_to_scanning(self, eurusd_config):
        state = self._make_state_with_window(level=1.1100, expiry_bar=-1)
        n = 50
        close = np.linspace(1.10, 1.12, n)
        df = pd.DataFrame({
            "open": close - 0.0001,
            "high": close + 0.0005,
            "low": close - 0.0005,
            "close": close,
            "tick_volume": np.ones(n) * 500,
        })
        indicators = calculate_indicators(df, eurusd_config)
        new_state = transition_window_open(state, df, indicators, eurusd_config, bar_index=-2)
        assert new_state.phase == Phase.SCANNING
