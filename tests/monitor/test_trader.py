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
        assert state.phase == Phase.IN_TRADE

    def test_live_mode_stores_ticket_in_state(self, mock_connection, eurusd_config, sym_info_dict):
        """active_ticket is set to the returned ticket on success."""
        live_executor = OrderExecutor(
            connection=mock_connection,
            configs={"EURUSD": eurusd_config},
            risk_pct=0.01,
            max_lot=0.5,
            demo_mode=False,
        )
        state = PhaseState(symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="LONG")
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        with patch("monitor.trader.place_market_order", return_value=777), \
             patch("monitor.trader.get_open_positions", return_value=[]), \
             patch("monitor.trader.get_symbol_info", return_value=sym_info_dict), \
             patch("monitor.trader.get_current_price", return_value=1.10010):
            live_executor.execute("EURUSD", state, indicators)
        assert state.active_ticket == 777

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

    def test_live_mode_short_sltp_calculated_from_entry_price(
        self, mock_connection, eurusd_config, sym_info_dict
    ):
        """SHORT order: SL above entry, TP below entry."""
        # Add short multipliers to config since eurusd_config only has long ones
        config = {**eurusd_config, "short_atr_sl_multiplier": 1.5, "short_atr_tp_multiplier": 10.0}
        live_executor = OrderExecutor(
            connection=mock_connection,
            configs={"EURUSD": config},
            risk_pct=0.01,
            max_lot=0.5,
            demo_mode=False,
        )
        state = PhaseState(
            symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="SHORT"
        )
        indicators = {"atr": 0.0003, "trend": "BEARISH"}
        entry_price = 1.10000  # bid for SHORT
        atr = 0.0003
        sl_mult = 1.5
        tp_mult = 10.0
        expected_sl = entry_price + atr * sl_mult  # SL above entry for SHORT
        expected_tp = entry_price - atr * tp_mult  # TP below entry for SHORT

        with patch("monitor.trader.place_market_order", return_value=888) as mock_place, \
             patch("monitor.trader.get_open_positions", return_value=[]), \
             patch("monitor.trader.get_symbol_info", return_value=sym_info_dict), \
             patch("monitor.trader.get_current_price", return_value=entry_price):
            live_executor.execute("EURUSD", state, indicators)

        call_kwargs = mock_place.call_args[1]
        assert abs(call_kwargs["sl"] - expected_sl) < 1e-6, "SL must be above entry for SHORT"
        assert abs(call_kwargs["tp"] - expected_tp) < 1e-6, "TP must be below entry for SHORT"

    def test_skips_if_tick_size_invalid(self, executor, sym_info_dict):
        """tick_size <= 0 in broker response must skip order, not produce wrong sizing."""
        state = PhaseState(symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="LONG")
        indicators = {"atr": 0.0003, "trend": "BULLISH"}
        bad_sym_info = {
            "point": 0.00001, "digits": 5,
            "trade_tick_value": 10.0, "trade_tick_size": 0.0,  # invalid
            "trade_contract_size": 100000,
            "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01,
        }
        with patch("monitor.trader.place_market_order") as mock_place, \
             patch("monitor.trader.get_open_positions", return_value=[]), \
             patch("monitor.trader.get_symbol_info", return_value=bad_sym_info), \
             patch("monitor.trader.get_current_price", return_value=1.10010):
            executor.execute("EURUSD", state, indicators)
            mock_place.assert_not_called()
        assert state.phase == Phase.SCANNING


class TestCheckInTrade:
    """Tests for OrderExecutor.check_in_trade()."""

    def _make_live_executor(self, mock_connection, eurusd_config):
        return OrderExecutor(
            connection=mock_connection,
            configs={"EURUSD": eurusd_config},
            risk_pct=0.01,
            max_lot=0.5,
            demo_mode=False,
        )

    def test_resets_when_position_closed(self, mock_connection, eurusd_config):
        """When active_ticket is gone from positions, reset to SCANNING."""
        executor = self._make_live_executor(mock_connection, eurusd_config)
        state = PhaseState(symbol="EURUSD", phase=Phase.IN_TRADE)
        state.active_ticket = 111
        with patch("monitor.trader.get_open_positions", return_value=[]):
            executor.check_in_trade("EURUSD", state)
        assert state.phase == Phase.SCANNING
        assert state.active_ticket is None

    def test_stays_in_trade_when_position_still_open(self, mock_connection, eurusd_config):
        """When active_ticket is still in positions, do not reset."""
        executor = self._make_live_executor(mock_connection, eurusd_config)
        state = PhaseState(symbol="EURUSD", phase=Phase.IN_TRADE)
        state.active_ticket = 111
        open_pos = [{"ticket": 111, "symbol": "EURUSD", "type": "BUY",
                     "volume": 0.01, "price_open": 1.1, "sl": 1.09, "tp": 1.12}]
        with patch("monitor.trader.get_open_positions", return_value=open_pos):
            executor.check_in_trade("EURUSD", state)
        assert state.phase == Phase.IN_TRADE
        assert state.active_ticket == 111

    def test_skips_when_not_in_trade(self, mock_connection, eurusd_config):
        """check_in_trade is a no-op when phase != IN_TRADE."""
        executor = self._make_live_executor(mock_connection, eurusd_config)
        state = PhaseState(symbol="EURUSD", phase=Phase.SCANNING)
        with patch("monitor.trader.get_open_positions") as mock_pos:
            executor.check_in_trade("EURUSD", state)
            mock_pos.assert_not_called()
        assert state.phase == Phase.SCANNING


class TestUpdateTrailingStop:
    """Tests for OrderExecutor.update_trailing_stop()."""

    def _make_live_executor(self, mock_connection, eurusd_config):
        return OrderExecutor(
            connection=mock_connection,
            configs={"EURUSD": eurusd_config},
            risk_pct=0.01,
            max_lot=0.5,
            demo_mode=False,
        )

    def test_moves_long_sl_up_when_profitable(self, mock_connection, eurusd_config):
        """LONG: candidate SL > current SL → call set_position_sltp."""
        executor = self._make_live_executor(mock_connection, eurusd_config)
        state = PhaseState(symbol="EURUSD", phase=Phase.IN_TRADE, direction="LONG")
        state.active_ticket = 111
        indicators = {"atr": 0.0010}
        # sl_mult = 1.5 (long_atr_sl_multiplier from eurusd_config)
        # candidate_sl = 1.1050 - 0.0010 * 1.5 = 1.1035
        # current_sl = 1.0900 → 1.1035 > 1.0900 → should move
        open_pos = [{"ticket": 111, "symbol": "EURUSD", "type": "BUY",
                     "volume": 0.01, "price_open": 1.1000, "sl": 1.0900, "tp": 1.1200}]
        with patch("monitor.trader.get_open_positions", return_value=open_pos), \
             patch("monitor.trader.get_current_price", return_value=1.1050), \
             patch("monitor.trader.set_position_sltp", return_value=True) as mock_sltp:
            executor.update_trailing_stop("EURUSD", state, indicators)
        mock_sltp.assert_called_once_with(111, "EURUSD", pytest.approx(1.1035, abs=1e-5), 1.1200)

    def test_does_not_widen_long_sl(self, mock_connection, eurusd_config):
        """LONG: candidate SL <= current SL → do NOT call set_position_sltp."""
        executor = self._make_live_executor(mock_connection, eurusd_config)
        state = PhaseState(symbol="EURUSD", phase=Phase.IN_TRADE, direction="LONG")
        state.active_ticket = 111
        indicators = {"atr": 0.0010}
        # candidate_sl = 1.0900 - 0.0015 = 1.0885 < current_sl 1.0950 → do NOT move
        open_pos = [{"ticket": 111, "symbol": "EURUSD", "type": "BUY",
                     "volume": 0.01, "price_open": 1.1000, "sl": 1.0950, "tp": 1.1200}]
        with patch("monitor.trader.get_open_positions", return_value=open_pos), \
             patch("monitor.trader.get_current_price", return_value=1.0900), \
             patch("monitor.trader.set_position_sltp") as mock_sltp:
            executor.update_trailing_stop("EURUSD", state, indicators)
        mock_sltp.assert_not_called()

    def test_moves_short_sl_down_when_profitable(self, mock_connection, eurusd_config):
        """SHORT: candidate SL < current SL → call set_position_sltp."""
        config = {**eurusd_config, "short_atr_sl_multiplier": 1.5}
        executor = OrderExecutor(connection=mock_connection, configs={"EURUSD": config},
                                  risk_pct=0.01, max_lot=0.5, demo_mode=False)
        state = PhaseState(symbol="EURUSD", phase=Phase.IN_TRADE, direction="SHORT")
        state.active_ticket = 222
        indicators = {"atr": 0.0010}
        # candidate_sl = 1.0950 + 0.0015 = 1.0965 < current_sl 1.1050 → should move
        open_pos = [{"ticket": 222, "symbol": "EURUSD", "type": "SELL",
                     "volume": 0.01, "price_open": 1.1000, "sl": 1.1050, "tp": 1.0800}]
        with patch("monitor.trader.get_open_positions", return_value=open_pos), \
             patch("monitor.trader.get_current_price", return_value=1.0950), \
             patch("monitor.trader.set_position_sltp", return_value=True) as mock_sltp:
            executor.update_trailing_stop("EURUSD", state, indicators)
        mock_sltp.assert_called_once_with(222, "EURUSD", pytest.approx(1.0965, abs=1e-5), 1.0800)

    def test_skips_when_not_in_trade(self, mock_connection, eurusd_config):
        """No-op when phase != IN_TRADE."""
        executor = self._make_live_executor(mock_connection, eurusd_config)
        state = PhaseState(symbol="EURUSD", phase=Phase.SCANNING)
        with patch("monitor.trader.get_open_positions") as mock_pos:
            executor.update_trailing_stop("EURUSD", state, {"atr": 0.001})
        mock_pos.assert_not_called()

    def test_skips_when_atr_invalid(self, mock_connection, eurusd_config):
        """No-op when ATR is zero."""
        executor = self._make_live_executor(mock_connection, eurusd_config)
        state = PhaseState(symbol="EURUSD", phase=Phase.IN_TRADE, direction="LONG")
        state.active_ticket = 111
        with patch("monitor.trader.get_open_positions") as mock_pos:
            executor.update_trailing_stop("EURUSD", state, {"atr": 0.0})
        mock_pos.assert_not_called()

    def test_skips_when_ticket_not_in_positions(self, mock_connection, eurusd_config):
        """No-op when active_ticket not found in open positions (race condition)."""
        executor = self._make_live_executor(mock_connection, eurusd_config)
        state = PhaseState(symbol="EURUSD", phase=Phase.IN_TRADE, direction="LONG")
        state.active_ticket = 999
        open_pos = [{"ticket": 111, "symbol": "EURUSD", "type": "BUY",
                     "volume": 0.01, "price_open": 1.1, "sl": 1.09, "tp": 1.12}]
        with patch("monitor.trader.get_open_positions", return_value=open_pos), \
             patch("monitor.trader.set_position_sltp") as mock_sltp:
            executor.update_trailing_stop("EURUSD", state, {"atr": 0.001})
        mock_sltp.assert_not_called()


class TestNotifierIntegration:
    """OrderExecutor calls notifier on key events when provided."""

    def _make_executor(self, mock_connection, eurusd_config, notifier=None):
        return OrderExecutor(
            connection=mock_connection,
            configs={"EURUSD": eurusd_config},
            risk_pct=0.01,
            max_lot=0.5,
            demo_mode=False,
            notifier=notifier,
        )

    def test_notifier_called_on_successful_order(self, mock_connection, eurusd_config, sym_info_dict):
        notifier = MagicMock()
        executor = self._make_executor(mock_connection, eurusd_config, notifier)
        state = PhaseState(symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="LONG")

        with patch("monitor.trader.get_open_positions", return_value=[]), \
             patch("monitor.trader.get_symbol_info", return_value=sym_info_dict), \
             patch("monitor.trader.get_current_price", return_value=1.1025), \
             patch("monitor.trader.place_market_order", return_value=55555):
            executor.execute("EURUSD", state, {"atr": 0.0010})

        notifier.notify_order_placed.assert_called_once()
        call_kwargs = notifier.notify_order_placed.call_args
        assert call_kwargs[0][0] == "EURUSD"
        assert call_kwargs[0][1] == "LONG"
        assert call_kwargs[0][6] == 55555  # ticket

    def test_no_notification_on_failed_order(self, mock_connection, eurusd_config, sym_info_dict):
        notifier = MagicMock()
        executor = self._make_executor(mock_connection, eurusd_config, notifier)
        state = PhaseState(symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="LONG")

        with patch("monitor.trader.get_open_positions", return_value=[]), \
             patch("monitor.trader.get_symbol_info", return_value=sym_info_dict), \
             patch("monitor.trader.get_current_price", return_value=1.1025), \
             patch("monitor.trader.place_market_order", return_value=None):
            executor.execute("EURUSD", state, {"atr": 0.0010})

        notifier.notify_order_placed.assert_not_called()

    def test_notifier_called_on_position_closed(self, mock_connection, eurusd_config):
        notifier = MagicMock()
        executor = self._make_executor(mock_connection, eurusd_config, notifier)
        state = PhaseState(symbol="EURUSD", phase=Phase.IN_TRADE, direction="LONG")
        state.active_ticket = 12345

        with patch("monitor.trader.get_open_positions", return_value=[]):
            executor.check_in_trade("EURUSD", state)

        notifier.notify_position_closed.assert_called_once_with("EURUSD", "LONG", 12345)

    def test_notifier_called_on_sl_moved(self, mock_connection, eurusd_config):
        notifier = MagicMock()
        executor = self._make_executor(mock_connection, eurusd_config, notifier)
        state = PhaseState(symbol="EURUSD", phase=Phase.IN_TRADE, direction="LONG")
        state.active_ticket = 111
        indicators = {"atr": 0.0010}
        open_pos = [{"ticket": 111, "symbol": "EURUSD", "type": "BUY",
                     "volume": 0.01, "price_open": 1.1000, "sl": 1.0900, "tp": 1.1200}]

        with patch("monitor.trader.get_open_positions", return_value=open_pos), \
             patch("monitor.trader.get_current_price", return_value=1.1050), \
             patch("monitor.trader.set_position_sltp", return_value=True):
            executor.update_trailing_stop("EURUSD", state, indicators)

        notifier.notify_sl_moved.assert_called_once()
        args = notifier.notify_sl_moved.call_args[0]
        assert args[0] == "EURUSD"
        assert args[1] == "LONG"

    def test_works_fine_without_notifier(self, mock_connection, eurusd_config, sym_info_dict):
        """notifier=None should not cause any error."""
        executor = self._make_executor(mock_connection, eurusd_config, notifier=None)
        state = PhaseState(symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="LONG")

        with patch("monitor.trader.get_open_positions", return_value=[]), \
             patch("monitor.trader.get_symbol_info", return_value=sym_info_dict), \
             patch("monitor.trader.get_current_price", return_value=1.1025), \
             patch("monitor.trader.place_market_order", return_value=99999):
            executor.execute("EURUSD", state, {"atr": 0.0010})

        assert state.phase == Phase.IN_TRADE  # succeeded without notifier
