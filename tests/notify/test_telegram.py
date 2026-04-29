import pytest
from unittest.mock import patch, MagicMock
from notify.telegram import TelegramNotifier


@pytest.fixture
def notifier():
    return TelegramNotifier(token="test_token", chat_id="123456")


@pytest.fixture
def mock_post():
    with patch("notify.telegram.requests.post") as m:
        m.return_value.status_code = 200
        yield m


class TestSend:
    def test_posts_to_correct_url(self, notifier, mock_post):
        notifier.send("hello")
        url = mock_post.call_args[0][0]
        assert "bottest_token" in url
        assert "sendMessage" in url

    def test_sends_chat_id_and_text(self, notifier, mock_post):
        notifier.send("hello")
        payload = mock_post.call_args[1]["json"]
        assert payload["chat_id"] == "123456"
        assert payload["text"] == "hello"

    def test_returns_true_on_200(self, notifier, mock_post):
        assert notifier.send("hello") is True

    def test_returns_false_on_non_200(self, notifier, mock_post):
        mock_post.return_value.status_code = 400
        assert notifier.send("hello") is False

    def test_returns_false_on_network_error(self, notifier, mock_post):
        mock_post.side_effect = Exception("network down")
        assert notifier.send("hello") is False

    def test_never_raises(self, notifier, mock_post):
        mock_post.side_effect = RuntimeError("unexpected")
        # should not raise
        result = notifier.send("hello")
        assert result is False


class TestNotifyOrderPlaced:
    def test_includes_symbol_and_direction(self, notifier, mock_post):
        notifier.notify_order_placed("EURUSD", "LONG", 0.02, 1.1025, 1.0988, 1.1225, 99001)
        text = mock_post.call_args[1]["json"]["text"]
        assert "EURUSD" in text
        assert "LONG" in text

    def test_includes_lot_and_ticket(self, notifier, mock_post):
        notifier.notify_order_placed("XAUUSD", "SHORT", 0.05, 2010.0, 2025.0, 1960.0, 77777)
        text = mock_post.call_args[1]["json"]["text"]
        assert "0.05" in text
        assert "77777" in text

    def test_includes_sl_and_tp(self, notifier, mock_post):
        notifier.notify_order_placed("GBPUSD", "LONG", 0.01, 1.2500, 1.2450, 1.2700, 11111)
        text = mock_post.call_args[1]["json"]["text"]
        assert "1.2450" in text
        assert "1.2700" in text


class TestNotifyPositionClosed:
    def test_includes_symbol_and_ticket(self, notifier, mock_post):
        notifier.notify_position_closed("EURUSD", "LONG", 55555)
        text = mock_post.call_args[1]["json"]["text"]
        assert "EURUSD" in text
        assert "55555" in text


class TestNotifySlMoved:
    def test_includes_symbol_and_both_sl_values(self, notifier, mock_post):
        notifier.notify_sl_moved("EURUSD", "LONG", 1.0900, 1.0935)
        text = mock_post.call_args[1]["json"]["text"]
        assert "EURUSD" in text
        assert "1.0900" in text
        assert "1.0935" in text


class TestNotifyError:
    def test_includes_context_and_message(self, notifier, mock_post):
        notifier.notify_error("EURUSD", "ATR calculation failed")
        text = mock_post.call_args[1]["json"]["text"]
        assert "EURUSD" in text
        assert "ATR calculation failed" in text

    def test_sends_even_if_context_is_none(self, notifier, mock_post):
        notifier.notify_error(None, "something broke")
        text = mock_post.call_args[1]["json"]["text"]
        assert "something broke" in text
