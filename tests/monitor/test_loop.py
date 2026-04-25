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
