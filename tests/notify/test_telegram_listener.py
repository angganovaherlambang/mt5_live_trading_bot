"""Tests for notify/telegram_listener.py"""
from unittest.mock import MagicMock, patch
import pytest

from notify.telegram_listener import TelegramListener


def _listener(get_status=None):
    return TelegramListener(
        token="test_token",
        chat_id="12345",
        get_status=get_status or (lambda: {}),
    )


def _update(update_id, text, chat_id="12345"):
    return {
        "update_id": update_id,
        "message": {"text": text, "chat": {"id": int(chat_id)}},
    }


class TestTelegramListenerHandle:
    def test_ignores_message_from_other_chat(self):
        listener = _listener()
        with patch.object(listener, "_send") as mock_send:
            listener._handle(_update(1, "/status", chat_id="99999"))
        mock_send.assert_not_called()

    def test_status_command_triggers_reply(self):
        listener = _listener()
        with patch.object(listener, "_reply_status") as mock_reply:
            listener._handle(_update(1, "/status"))
        mock_reply.assert_called_once()

    def test_unknown_command_is_ignored(self):
        listener = _listener()
        with patch.object(listener, "_send") as mock_send:
            listener._handle(_update(1, "/foo"))
        mock_send.assert_not_called()

    def test_empty_message_is_ignored(self):
        listener = _listener()
        with patch.object(listener, "_send") as mock_send:
            listener._handle({"update_id": 1, "message": {"chat": {"id": 12345}}})
        mock_send.assert_not_called()


class TestTelegramListenerReplyStatus:
    def test_reply_contains_all_symbols(self):
        status = {
            "EURUSD": {"phase": "SCANNING", "direction": None, "ticket": None},
            "GBPUSD": {"phase": "IN_TRADE", "direction": "LONG", "ticket": 42},
        }
        listener = _listener(get_status=lambda: status)
        with patch.object(listener, "_send") as mock_send:
            listener._reply_status()
        text = mock_send.call_args[0][0]
        assert "EURUSD" in text
        assert "GBPUSD" in text
        assert "SCANNING" in text
        assert "IN_TRADE" in text

    def test_reply_shows_direction_when_in_trade(self):
        status = {"EURUSD": {"phase": "IN_TRADE", "direction": "LONG", "ticket": 99}}
        listener = _listener(get_status=lambda: status)
        with patch.object(listener, "_send") as mock_send:
            listener._reply_status()
        text = mock_send.call_args[0][0]
        assert "LONG" in text
        assert "99" in text

    def test_send_posts_to_sendmessage_endpoint(self):
        listener = _listener()
        with patch("notify.telegram_listener.requests.post") as mock_post:
            listener._send("hello")
        url = mock_post.call_args[0][0]
        assert "sendMessage" in url
        assert "test_token" in url

    def test_send_swallows_exceptions(self):
        listener = _listener()
        with patch("notify.telegram_listener.requests.post", side_effect=ConnectionError):
            listener._send("hello")  # must not raise


class TestTelegramListenerFetchUpdates:
    def test_returns_empty_on_non_200(self):
        listener = _listener()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        with patch("notify.telegram_listener.requests.get", return_value=mock_resp):
            result = listener._fetch_updates()
        assert result == []

    def test_returns_result_list_on_success(self):
        listener = _listener()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": [_update(5, "/status")]}
        with patch("notify.telegram_listener.requests.get", return_value=mock_resp):
            result = listener._fetch_updates()
        assert len(result) == 1
        assert result[0]["update_id"] == 5


class TestNewCommands:
    def _listener_with_callbacks(self, positions=None, balance=None):
        return TelegramListener(
            token="tok",
            chat_id="12345",
            get_status=lambda: {},
            get_positions=positions or (lambda: []),
            get_balance=balance or (lambda: None),
        )

    def test_positions_command_triggers_reply(self):
        listener = self._listener_with_callbacks()
        with patch.object(listener, "_reply_positions") as mock_fn:
            listener._handle(_update(1, "/positions"))
        mock_fn.assert_called_once()

    def test_balance_command_triggers_reply(self):
        listener = self._listener_with_callbacks()
        with patch.object(listener, "_reply_balance") as mock_fn:
            listener._handle(_update(1, "/balance"))
        mock_fn.assert_called_once()

    def test_help_command_triggers_reply(self):
        listener = self._listener_with_callbacks()
        with patch.object(listener, "_reply_help") as mock_fn:
            listener._handle(_update(1, "/help"))
        mock_fn.assert_called_once()

    def test_positions_reply_shows_open_trades(self):
        positions = [
            {"symbol": "EURUSD", "type": "BUY", "volume": 0.01,
             "price_open": 1.1000, "profit": 45.50, "ticket": 111},
        ]
        listener = self._listener_with_callbacks(positions=lambda: positions)
        with patch.object(listener, "_send") as mock_send:
            listener._reply_positions()
        text = mock_send.call_args[0][0]
        assert "EURUSD" in text
        assert "45.50" in text

    def test_positions_reply_shows_no_positions_message(self):
        listener = self._listener_with_callbacks(positions=lambda: [])
        with patch.object(listener, "_send") as mock_send:
            listener._reply_positions()
        text = mock_send.call_args[0][0]
        assert "no open" in text.lower() or "0" in text

    def test_balance_reply_shows_balance_and_equity(self):
        balance_info = {"balance": 10250.75, "equity": 10310.20, "login": 12345}
        listener = self._listener_with_callbacks(balance=lambda: balance_info)
        with patch.object(listener, "_send") as mock_send:
            listener._reply_balance()
        text = mock_send.call_args[0][0]
        assert "10250" in text
        assert "10310" in text

    def test_balance_reply_handles_no_connection(self):
        listener = self._listener_with_callbacks(balance=lambda: None)
        with patch.object(listener, "_send") as mock_send:
            listener._reply_balance()
        text = mock_send.call_args[0][0]
        assert "unavailable" in text.lower() or "error" in text.lower() or "connect" in text.lower()

    def test_help_reply_lists_all_commands(self):
        listener = self._listener_with_callbacks()
        with patch.object(listener, "_send") as mock_send:
            listener._reply_help()
        text = mock_send.call_args[0][0]
        for cmd in ("/status", "/positions", "/balance", "/help"):
            assert cmd in text
