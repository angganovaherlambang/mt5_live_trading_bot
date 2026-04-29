import queue
import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock, patch
from monitor.loop import MonitorLoop
from core.state import PhaseState, Phase


@pytest.fixture
def mock_connection(mocker):
    conn = MagicMock()
    conn.is_connected = True
    conn.fetch_ohlcv.return_value = _make_df(150)
    conn.get_account_info.return_value = {"balance": 10000.0, "equity": 10000.0, "login": 12345}
    return conn


def _make_df(n: int) -> pd.DataFrame:
    np.random.seed(0)
    close = 1.1 + np.cumsum(np.random.randn(n) * 0.0002)
    return pd.DataFrame({
        "open": close - 0.0001, "high": close + 0.0004,
        "low": close - 0.0004, "close": close,
        "tick_volume": np.ones(n) * 500,
    })


class TestMonitorLoop:
    def test_initialises_states_for_all_symbols(self, mock_connection, eurusd_config):
        symbols = ["EURUSD", "XAUUSD"]
        configs = {"EURUSD": eurusd_config, "XAUUSD": eurusd_config}
        q = queue.Queue()
        loop = MonitorLoop(connection=mock_connection, configs=configs, symbols=symbols, update_queue=q)
        assert set(loop.states.keys()) == {"EURUSD", "XAUUSD"}
        for s in loop.states.values():
            assert s.phase == Phase.SCANNING

    def test_process_symbol_enqueues_update(self, mock_connection, eurusd_config):
        symbols = ["EURUSD"]
        configs = {"EURUSD": eurusd_config}
        q = queue.Queue()
        loop = MonitorLoop(connection=mock_connection, configs=configs, symbols=symbols, update_queue=q)
        loop._process_symbol("EURUSD")
        assert not q.empty()
        update = q.get_nowait()
        assert update["symbol"] == "EURUSD"
        assert "phase" in update

    def test_process_symbol_skips_on_no_data(self, mock_connection, eurusd_config):
        mock_connection.fetch_ohlcv.return_value = None
        symbols = ["EURUSD"]
        configs = {"EURUSD": eurusd_config}
        q = queue.Queue()
        loop = MonitorLoop(connection=mock_connection, configs=configs, symbols=symbols, update_queue=q)
        loop._process_symbol("EURUSD")
        assert q.empty()

    def test_executor_called_when_awaiting_entry(self, mock_connection, eurusd_config):
        """When state reaches AWAITING_ENTRY, order_executor.execute() is called."""
        symbols = ["EURUSD"]
        configs = {"EURUSD": eurusd_config}
        q = queue.Queue()

        mock_executor = MagicMock()
        loop = MonitorLoop(
            connection=mock_connection,
            configs=configs,
            symbols=symbols,
            update_queue=q,
            order_executor=mock_executor,
        )

        # Force state to AWAITING_ENTRY
        loop.states["EURUSD"] = PhaseState(
            symbol="EURUSD", phase=Phase.AWAITING_ENTRY, direction="LONG"
        )

        # Patch advance_state to preserve the AWAITING_ENTRY state (no transition)
        with patch("monitor.loop.advance_state", side_effect=lambda s, *a, **k: s):
            loop._process_symbol("EURUSD")

        mock_executor.execute.assert_called_once()
        call_args = mock_executor.execute.call_args
        assert call_args[0][1].phase == Phase.AWAITING_ENTRY

    def test_executor_called_but_skips_when_scanning(self, mock_connection, eurusd_config):
        """Executor.execute() is called, but its internal guard skips order when phase is SCANNING."""
        symbols = ["EURUSD"]
        configs = {"EURUSD": eurusd_config}
        q = queue.Queue()
        mock_executor = MagicMock()
        loop = MonitorLoop(
            connection=mock_connection,
            configs=configs,
            symbols=symbols,
            update_queue=q,
            order_executor=mock_executor,
        )
        # State is SCANNING
        loop.states["EURUSD"] = PhaseState(symbol="EURUSD", phase=Phase.SCANNING)

        with patch("monitor.loop.advance_state", side_effect=lambda s, *a, **k: s):
            loop._process_symbol("EURUSD")

        # Executor was still called — the guard is inside OrderExecutor.execute(), not MonitorLoop
        mock_executor.execute.assert_called_once()
        call_args = mock_executor.execute.call_args
        assert call_args[0][1].phase == Phase.SCANNING

    def test_in_trade_calls_check_in_trade_not_execute(self, mock_connection, eurusd_config):
        """When phase is IN_TRADE, check_in_trade() is called; execute() is NOT."""
        symbols = ["EURUSD"]
        configs = {"EURUSD": eurusd_config}
        q = queue.Queue()
        mock_executor = MagicMock()
        loop = MonitorLoop(
            connection=mock_connection,
            configs=configs,
            symbols=symbols,
            update_queue=q,
            order_executor=mock_executor,
        )
        loop.states["EURUSD"] = PhaseState(symbol="EURUSD", phase=Phase.IN_TRADE)
        loop.states["EURUSD"].active_ticket = 42

        loop._process_symbol("EURUSD")

        mock_executor.check_in_trade.assert_called_once_with("EURUSD", loop.states["EURUSD"])
        mock_executor.execute.assert_not_called()

    def test_in_trade_still_enqueues_update(self, mock_connection, eurusd_config):
        """IN_TRADE path must still put an update on the queue."""
        symbols = ["EURUSD"]
        configs = {"EURUSD": eurusd_config}
        q = queue.Queue()
        mock_executor = MagicMock()
        loop = MonitorLoop(
            connection=mock_connection,
            configs=configs,
            symbols=symbols,
            update_queue=q,
            order_executor=mock_executor,
        )
        loop.states["EURUSD"] = PhaseState(symbol="EURUSD", phase=Phase.IN_TRADE)
        loop.states["EURUSD"].active_ticket = 42

        loop._process_symbol("EURUSD")

        assert not q.empty()
        update = q.get_nowait()
        assert update["symbol"] == "EURUSD"
        assert update["phase"] == "IN_TRADE"

    def test_in_trade_skips_advance_state(self, mock_connection, eurusd_config):
        """advance_state is NOT called when phase is IN_TRADE."""
        symbols = ["EURUSD"]
        configs = {"EURUSD": eurusd_config}
        q = queue.Queue()
        mock_executor = MagicMock()
        loop = MonitorLoop(
            connection=mock_connection,
            configs=configs,
            symbols=symbols,
            update_queue=q,
            order_executor=mock_executor,
        )
        loop.states["EURUSD"] = PhaseState(symbol="EURUSD", phase=Phase.IN_TRADE)
        loop.states["EURUSD"].active_ticket = 42

        with patch("monitor.loop.advance_state") as mock_advance:
            loop._process_symbol("EURUSD")
            mock_advance.assert_not_called()

    def test_in_trade_calls_update_trailing_stop_when_still_open(self, mock_connection, eurusd_config):
        """After check_in_trade() leaves state as IN_TRADE, update_trailing_stop() is called."""
        symbols = ["EURUSD"]
        configs = {"EURUSD": eurusd_config}
        q = queue.Queue()
        mock_executor = MagicMock()
        # check_in_trade does NOT reset state (position still open)
        mock_executor.check_in_trade.side_effect = lambda sym, st: None
        loop = MonitorLoop(
            connection=mock_connection, configs=configs, symbols=symbols,
            update_queue=q, order_executor=mock_executor,
        )
        loop.states["EURUSD"] = PhaseState(symbol="EURUSD", phase=Phase.IN_TRADE)
        loop.states["EURUSD"].active_ticket = 42

        loop._process_symbol("EURUSD")

        mock_executor.update_trailing_stop.assert_called_once()

    def test_in_trade_skips_trailing_stop_when_position_closed(self, mock_connection, eurusd_config):
        """If check_in_trade() resets state to SCANNING, update_trailing_stop() is NOT called."""
        symbols = ["EURUSD"]
        configs = {"EURUSD": eurusd_config}
        q = queue.Queue()
        mock_executor = MagicMock()

        def reset_state(sym, st):
            st.reset()  # simulate position closed by broker

        mock_executor.check_in_trade.side_effect = reset_state
        loop = MonitorLoop(
            connection=mock_connection, configs=configs, symbols=symbols,
            update_queue=q, order_executor=mock_executor,
        )
        loop.states["EURUSD"] = PhaseState(symbol="EURUSD", phase=Phase.IN_TRADE)
        loop.states["EURUSD"].active_ticket = 42

        loop._process_symbol("EURUSD")

        mock_executor.update_trailing_stop.assert_not_called()
