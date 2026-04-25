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
def sym_info_dict():
    """Broker specs for EURUSD — used to mock get_symbol_info()."""
    return {
        "point": 0.00001,
        "digits": 5,
        "trade_tick_value": 10.0,
        "trade_tick_size": 0.00001,
        "trade_contract_size": 100000,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
    }


@pytest.fixture
def executor(mock_connection, eurusd_config):
    return OrderExecutor(
        connection=mock_connection,
        configs={"EURUSD": eurusd_config},
        risk_pct=0.01,
        max_lot=0.5,
        demo_mode=True,
    )


class TestOrderExecutor:
    def test_skips_if_not_awaiting_entry(self, executor):
        state = PhaseState(symbol="EURUSD", phase=Phase.SCANNING)
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        with patch("monitor.trader.place_market_order") as mock_place:
            executor.execute("EURUSD", state, indicators)
            mock_place.assert_not_called()

    def test_demo_mode_logs_and_skips_place_order(self, executor, sym_info_dict):
        """Demo mode must never call place_market_order."""
        state = PhaseState(
            symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="LONG"
        )
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        with patch("monitor.trader.place_market_order") as mock_place, \
             patch("monitor.trader.get_open_positions", return_value=[]), \
             patch("monitor.trader.get_symbol_info", return_value=sym_info_dict), \
             patch("monitor.trader.get_current_price", return_value=1.10010):
            executor.execute("EURUSD", state, indicators)
            mock_place.assert_not_called()
        assert state.phase == Phase.SCANNING

    def test_resets_state_to_scanning_after_demo(self, executor, sym_info_dict):
        state = PhaseState(
            symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="LONG"
        )
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        with patch("monitor.trader.get_open_positions", return_value=[]), \
             patch("monitor.trader.get_symbol_info", return_value=sym_info_dict), \
             patch("monitor.trader.get_current_price", return_value=1.10010):
            executor.execute("EURUSD", state, indicators)
        assert state.phase == Phase.SCANNING

    def test_live_mode_places_order(self, mock_connection, eurusd_config, sym_info_dict):
        """Live mode (demo_mode=False) calls place_market_order."""
        live_executor = OrderExecutor(
            connection=mock_connection,
            configs={"EURUSD": eurusd_config},
            risk_pct=0.01,
            max_lot=0.5,
            demo_mode=False,
        )
        state = PhaseState(
            symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="LONG"
        )
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        with patch("monitor.trader.place_market_order", return_value=999) as mock_place, \
             patch("monitor.trader.get_open_positions", return_value=[]), \
             patch("monitor.trader.get_symbol_info", return_value=sym_info_dict), \
             patch("monitor.trader.get_current_price", return_value=1.10010):
            live_executor.execute("EURUSD", state, indicators)
            mock_place.assert_called_once()
        assert state.phase == Phase.SCANNING

    def test_live_mode_sltp_calculated_from_entry_price(
        self, mock_connection, eurusd_config, sym_info_dict
    ):
        """SL/TP must be calculated from get_current_price(), not 0.0."""
        live_executor = OrderExecutor(
            connection=mock_connection,
            configs={"EURUSD": eurusd_config},
            risk_pct=0.01,
            max_lot=0.5,
            demo_mode=False,
        )
        state = PhaseState(
            symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="LONG"
        )
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        entry_price = 1.10010
        atr = 0.0003
        sl_mult = eurusd_config["long_atr_sl_multiplier"]  # 1.5
        tp_mult = eurusd_config["long_atr_tp_multiplier"]  # 10.0
        expected_sl = entry_price - atr * sl_mult
        expected_tp = entry_price + atr * tp_mult

        with patch("monitor.trader.place_market_order", return_value=999) as mock_place, \
             patch("monitor.trader.get_open_positions", return_value=[]), \
             patch("monitor.trader.get_symbol_info", return_value=sym_info_dict), \
             patch("monitor.trader.get_current_price", return_value=entry_price):
            live_executor.execute("EURUSD", state, indicators)

        call_kwargs = mock_place.call_args[1]
        assert abs(call_kwargs["sl"] - expected_sl) < 1e-6, "SL must be based on entry price"
        assert abs(call_kwargs["tp"] - expected_tp) < 1e-6, "TP must be based on entry price"

    def test_resets_state_if_order_fails(self, mock_connection, eurusd_config, sym_info_dict):
        """State resets even when place_market_order returns None."""
        live_executor = OrderExecutor(
            connection=mock_connection,
            configs={"EURUSD": eurusd_config},
            risk_pct=0.01,
            max_lot=0.5,
            demo_mode=False,
        )
        state = PhaseState(
            symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="LONG"
        )
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        with patch("monitor.trader.place_market_order", return_value=None), \
             patch("monitor.trader.get_open_positions", return_value=[]), \
             patch("monitor.trader.get_symbol_info", return_value=sym_info_dict), \
             patch("monitor.trader.get_current_price", return_value=1.10010):
            live_executor.execute("EURUSD", state, indicators)
        assert state.phase == Phase.SCANNING

    def test_skips_if_position_already_open(self, executor, sym_info_dict):
        state = PhaseState(
            symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="LONG"
        )
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        existing = [{"ticket": 1, "symbol": "EURUSD", "type": "BUY",
                     "volume": 0.01, "price_open": 1.1, "sl": 1.09, "tp": 1.12}]
        with patch("monitor.trader.place_market_order") as mock_place, \
             patch("monitor.trader.get_open_positions", return_value=existing):
            executor.execute("EURUSD", state, indicators)
            mock_place.assert_not_called()
        assert state.phase == Phase.SCANNING

    def test_skips_if_no_config(self, mock_connection):
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

    def test_skips_if_atr_invalid(self, executor, sym_info_dict):
        state = PhaseState(symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="LONG")
        indicators = {"atr": 0.0, "trend": "BULLISH"}
        with patch("monitor.trader.place_market_order") as mock_place, \
             patch("monitor.trader.get_open_positions", return_value=[]):
            executor.execute("EURUSD", state, indicators)
            mock_place.assert_not_called()
        assert state.phase == Phase.SCANNING

    def test_skips_if_account_info_none(self, mock_connection, eurusd_config):
        mock_connection.get_account_info.return_value = None
        exec_ = OrderExecutor(
            connection=mock_connection,
            configs={"EURUSD": eurusd_config},
            risk_pct=0.01,
            max_lot=0.5,
            demo_mode=True,
        )
        state = PhaseState(symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="LONG")
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        with patch("monitor.trader.place_market_order") as mock_place, \
             patch("monitor.trader.get_open_positions", return_value=[]):
            exec_.execute("EURUSD", state, indicators)
            mock_place.assert_not_called()
        assert state.phase == Phase.SCANNING

    def test_skips_if_symbol_info_unavailable(self, executor):
        state = PhaseState(symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="LONG")
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        with patch("monitor.trader.place_market_order") as mock_place, \
             patch("monitor.trader.get_open_positions", return_value=[]), \
             patch("monitor.trader.get_symbol_info", return_value=None):
            executor.execute("EURUSD", state, indicators)
            mock_place.assert_not_called()
        assert state.phase == Phase.SCANNING

    def test_skips_if_current_price_unavailable(self, executor, sym_info_dict):
        state = PhaseState(symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="LONG")
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        with patch("monitor.trader.place_market_order") as mock_place, \
             patch("monitor.trader.get_open_positions", return_value=[]), \
             patch("monitor.trader.get_symbol_info", return_value=sym_info_dict), \
             patch("monitor.trader.get_current_price", return_value=None):
            executor.execute("EURUSD", state, indicators)
            mock_place.assert_not_called()
        assert state.phase == Phase.SCANNING
