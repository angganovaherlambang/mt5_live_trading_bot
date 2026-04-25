import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_mt5(mocker):
    m = mocker.patch("mt5.orders.mt5")
    m.ORDER_TYPE_BUY = 0
    m.ORDER_TYPE_SELL = 1
    m.TRADE_ACTION_DEAL = 1
    m.ORDER_TIME_GTC = 1
    m.ORDER_FILLING_IOC = 2
    # Successful order result
    result = MagicMock()
    result.retcode = 10009  # TRADE_RETCODE_DONE
    result.order = 111222
    m.order_send.return_value = result
    # Symbol info
    sym_info = MagicMock()
    sym_info.point = 0.00001
    sym_info.digits = 5
    m.symbol_info.return_value = sym_info
    # Tick
    tick = MagicMock()
    tick.ask = 1.10010
    tick.bid = 1.10000
    m.symbol_info_tick.return_value = tick
    return m


class TestPlaceMarketOrder:
    def test_long_order_sends_buy(self, mock_mt5):
        from mt5.orders import place_market_order
        result = place_market_order(
            symbol="EURUSD",
            direction="LONG",
            lot=0.01,
            sl=1.0955,
            tp=1.1100,
            deviation=10,
        )
        assert result is not None
        call_args = mock_mt5.order_send.call_args[0][0]
        assert call_args["type"] == mock_mt5.ORDER_TYPE_BUY

    def test_short_order_sends_sell(self, mock_mt5):
        from mt5.orders import place_market_order
        result = place_market_order(
            symbol="EURUSD",
            direction="SHORT",
            lot=0.01,
            sl=1.1050,
            tp=1.0900,
            deviation=10,
        )
        call_args = mock_mt5.order_send.call_args[0][0]
        assert call_args["type"] == mock_mt5.ORDER_TYPE_SELL

    def test_returns_none_on_mt5_failure(self, mock_mt5):
        from mt5.orders import place_market_order
        mock_mt5.order_send.return_value.retcode = 10004  # REQUOTE
        result = place_market_order("EURUSD", "LONG", 0.01, 1.09, 1.11, 10)
        assert result is None

    def test_sl_tp_rounded_to_digits(self, mock_mt5):
        from mt5.orders import place_market_order
        place_market_order("EURUSD", "LONG", 0.01, 1.09551234, 1.10998765, 10)
        call_args = mock_mt5.order_send.call_args[0][0]
        # digits=5, so SL and TP should have at most 5 decimal places
        assert len(str(call_args["sl"]).split(".")[-1]) <= 5
        assert len(str(call_args["tp"]).split(".")[-1]) <= 5


class TestGetOpenPositions:
    def test_returns_list_of_dicts(self, mock_mt5):
        from mt5.orders import get_open_positions
        pos = MagicMock()
        pos.ticket = 111
        pos.symbol = "EURUSD"
        pos.type = 0  # BUY
        pos.volume = 0.01
        pos.price_open = 1.1000
        pos.sl = 1.0950
        pos.tp = 1.1100
        mock_mt5.positions_get.return_value = [pos]
        result = get_open_positions("EURUSD")
        assert len(result) == 1
        assert result[0]["ticket"] == 111
        assert result[0]["symbol"] == "EURUSD"

    def test_returns_empty_list_when_no_positions(self, mock_mt5):
        from mt5.orders import get_open_positions
        mock_mt5.positions_get.return_value = []
        assert get_open_positions("EURUSD") == []
