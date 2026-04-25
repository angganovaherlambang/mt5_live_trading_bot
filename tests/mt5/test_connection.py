import pytest
from unittest.mock import MagicMock, patch
from mt5.connection import MT5Connection


@pytest.fixture
def mock_mt5(mocker):
    """Patch the MetaTrader5 module everywhere it's imported."""
    mt5_mock = mocker.patch("mt5.connection.mt5")
    mt5_mock.initialize.return_value = True
    mt5_mock.account_info.return_value = MagicMock(balance=10000.0, equity=10000.0, login=12345)
    mt5_mock.last_error.return_value = (0, "No error")
    return mt5_mock


class TestMT5Connection:
    def test_connect_returns_true_on_success(self, mock_mt5):
        conn = MT5Connection()
        assert conn.connect() is True
        assert conn.is_connected is True

    def test_connect_returns_false_on_mt5_failure(self, mock_mt5):
        mock_mt5.initialize.return_value = False
        conn = MT5Connection()
        assert conn.connect() is False
        assert conn.is_connected is False

    def test_disconnect_calls_shutdown(self, mock_mt5):
        conn = MT5Connection()
        conn.connect()
        conn.disconnect()
        mock_mt5.shutdown.assert_called_once()
        assert conn.is_connected is False

    def test_get_account_info_returns_dict(self, mock_mt5):
        conn = MT5Connection()
        conn.connect()
        info = conn.get_account_info()
        assert "balance" in info
        assert info["balance"] == 10000.0

    def test_get_account_info_returns_none_when_disconnected(self, mock_mt5):
        conn = MT5Connection()
        info = conn.get_account_info()
        assert info is None

    def test_reconnect_increments_attempt_counter(self, mock_mt5, mocker):
        mocker.patch("mt5.connection.time.sleep")  # don't actually sleep
        conn = MT5Connection()
        conn.connect()
        conn._is_connected = False  # simulate drop
        conn.reconnect()
        assert conn.reconnect_attempts >= 1
