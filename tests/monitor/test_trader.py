import pytest
from unittest.mock import MagicMock, patch
from core.state import PhaseState, Phase
from monitor.trader import OrderExecutor


@pytest.fixture
def mock_connection():
    conn = MagicMock()
    conn.is_connected = True
    conn.get_account_info.return_value = {
        "balance": 10000.0,
        "equity": 10000.0,
        "login": 12345,
    }
    return conn


@pytest.fixture
def executor(mock_connection, eurusd_config):
    return OrderExecutor(
        connection=mock_connection,
        configs={"EURUSD": eurusd_config},
        risk_pct=0.01,
        max_lot=0.5,
        demo_mode=True,
    )


@pytest.fixture
def live_executor(mock_connection, eurusd_config):
    """Executor with demo_mode=False so place_market_order is actually called."""
    return OrderExecutor(
        connection=mock_connection,
        configs={"EURUSD": eurusd_config},
        risk_pct=0.01,
        max_lot=0.5,
        demo_mode=False,
    )


class TestOrderExecutor:
    def test_skips_if_not_awaiting_entry(self, executor, eurusd_config):
        state = PhaseState(symbol="EURUSD", phase=Phase.SCANNING)
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        with patch("monitor.trader.place_market_order") as mock_place:
            executor.execute("EURUSD", state, indicators)
            mock_place.assert_not_called()

    def test_places_order_when_awaiting_entry_long(self, live_executor, eurusd_config):
        state = PhaseState(
            symbol="EURUSD",
            phase=Phase.AWAITING_ENTRY,
            direction="LONG",
        )
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        with patch("monitor.trader.place_market_order", return_value=999) as mock_place, \
             patch("monitor.trader.get_open_positions", return_value=[]):
            live_executor.execute("EURUSD", state, indicators)
            mock_place.assert_called_once()
            call_kwargs = mock_place.call_args
            assert call_kwargs[1]["direction"] == "LONG" or call_kwargs[0][1] == "LONG"

    def test_resets_state_to_scanning_after_order(self, live_executor, eurusd_config):
        state = PhaseState(
            symbol="EURUSD",
            phase=Phase.AWAITING_ENTRY,
            direction="LONG",
        )
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        with patch("monitor.trader.place_market_order", return_value=999), \
             patch("monitor.trader.get_open_positions", return_value=[]):
            live_executor.execute("EURUSD", state, indicators)
        assert state.phase == Phase.SCANNING

    def test_skips_if_position_already_open(self, executor, eurusd_config):
        state = PhaseState(
            symbol="EURUSD",
            phase=Phase.AWAITING_ENTRY,
            direction="LONG",
        )
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        existing = [{"ticket": 1, "symbol": "EURUSD", "type": "BUY",
                     "volume": 0.01, "price_open": 1.1, "sl": 1.09, "tp": 1.12}]
        with patch("monitor.trader.place_market_order") as mock_place, \
             patch("monitor.trader.get_open_positions", return_value=existing):
            executor.execute("EURUSD", state, indicators)
            mock_place.assert_not_called()
        # State must still reset
        assert state.phase == Phase.SCANNING

    def test_resets_state_if_order_fails(self, live_executor, eurusd_config):
        state = PhaseState(
            symbol="EURUSD",
            phase=Phase.AWAITING_ENTRY,
            direction="LONG",
        )
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        with patch("monitor.trader.place_market_order", return_value=None), \
             patch("monitor.trader.get_open_positions", return_value=[]):
            live_executor.execute("EURUSD", state, indicators)
        # Even on failure, reset to avoid infinite retry
        assert state.phase == Phase.SCANNING

    def test_skips_if_no_config(self, mock_connection, eurusd_config):
        executor = OrderExecutor(
            connection=mock_connection,
            configs={},  # no EURUSD config
            risk_pct=0.01,
            max_lot=0.5,
            demo_mode=True,
        )
        state = PhaseState(symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="LONG")
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        with patch("monitor.trader.place_market_order") as mock_place:
            executor.execute("EURUSD", state, indicators)
            mock_place.assert_not_called()
