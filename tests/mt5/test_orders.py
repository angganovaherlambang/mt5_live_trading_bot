import pytest
from unittest.mock import MagicMock

from mt5.orders import place_market_order, get_open_positions, close_position, get_symbol_info, get_current_price


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
    # Symbol info — includes broker contract specs for position sizing
    sym_info = MagicMock()
    sym_info.point = 0.00001
    sym_info.digits = 5
    sym_info.trade_tick_value = 10.0
    sym_info.trade_tick_size = 0.00001
    sym_info.trade_contract_size = 100000
    sym_info.volume_min = 0.01
    sym_info.volume_max = 100.0
    sym_info.volume_step = 0.01
    m.symbol_info.return_value = sym_info
    # Tick
    tick = MagicMock()
    tick.ask = 1.10010
    tick.bid = 1.10000
    m.symbol_info_tick.return_value = tick
    return m


class TestPlaceMarketOrder:
    def test_long_order_sends_buy(self, mock_mt5):
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
        mock_mt5.order_send.return_value.retcode = 10004  # REQUOTE
        result = place_market_order("EURUSD", "LONG", 0.01, 1.09, 1.11, 10)
        assert result is None

    def test_sl_tp_rounded_to_digits(self, mock_mt5):
        place_market_order("EURUSD", "LONG", 0.01, 1.09551234, 1.10998765, 10)
        call_args = mock_mt5.order_send.call_args[0][0]
        assert call_args["sl"] == round(1.09551234, 5)
        assert call_args["tp"] == round(1.10998765, 5)


class TestGetOpenPositions:
    def test_returns_list_of_dicts(self, mock_mt5):
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
        mock_mt5.positions_get.return_value = []
        assert get_open_positions("EURUSD") == []


class TestClosePosition:
    def test_returns_true_on_success(self, mock_mt5):
        result = close_position(ticket=111, symbol="EURUSD", lot=0.01, direction="LONG")
        assert result is True
        call_args = mock_mt5.order_send.call_args[0][0]
        assert call_args["position"] == 111
        assert call_args["type"] == mock_mt5.ORDER_TYPE_SELL  # closing LONG = SELL

    def test_returns_false_on_failure(self, mock_mt5):
        mock_mt5.order_send.return_value.retcode = 10004
        result = close_position(ticket=111, symbol="EURUSD", lot=0.01, direction="LONG")
        assert result is False

    def test_returns_false_when_no_tick(self, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = None
        result = close_position(ticket=111, symbol="EURUSD", lot=0.01, direction="LONG")
        assert result is False
        mock_mt5.order_send.assert_not_called()


class TestGetSymbolInfo:
    def test_returns_dict_with_required_keys(self, mock_mt5):
        result = get_symbol_info("EURUSD")
        assert result is not None
        for key in ("point", "digits", "trade_tick_value", "trade_tick_size",
                    "trade_contract_size", "volume_min", "volume_max", "volume_step"):
            assert key in result, f"missing key: {key}"

    def test_values_match_mt5_symbol_info(self, mock_mt5):
        result = get_symbol_info("EURUSD")
        assert result["point"] == 0.00001
        assert result["trade_tick_value"] == 10.0
        assert result["volume_min"] == 0.01

    def test_returns_none_when_symbol_not_found(self, mock_mt5):
        mock_mt5.symbol_info.return_value = None
        assert get_symbol_info("INVALID") is None


class TestGetCurrentPrice:
    def test_long_returns_ask(self, mock_mt5):
        assert get_current_price("EURUSD", "LONG") == 1.10010

    def test_short_returns_bid(self, mock_mt5):
        assert get_current_price("EURUSD", "SHORT") == 1.10000

    def test_returns_none_when_tick_unavailable(self, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = None
        assert get_current_price("EURUSD", "LONG") is None

    def test_returns_none_on_invalid_direction(self, mock_mt5):
        from mt5.orders import get_current_price
        assert get_current_price("EURUSD", "INVALID") is None

    def test_returns_none_when_mt5_unavailable(self, mocker):
        from mt5 import orders as orders_module
        mocker.patch.object(orders_module, "mt5", None)
        from mt5.orders import get_current_price
        assert get_current_price("EURUSD", "LONG") is None
