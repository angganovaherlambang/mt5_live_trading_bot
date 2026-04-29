import pytest
from unittest.mock import MagicMock

from mt5.orders import place_market_order, get_open_positions, close_position, get_symbol_info, get_current_price, set_position_sltp, get_daily_deals


@pytest.fixture
def mock_mt5(mocker):
    m = mocker.patch("mt5.orders.mt5")
    m.ORDER_TYPE_BUY = 0
    m.ORDER_TYPE_SELL = 1
    m.TRADE_ACTION_DEAL = 1
    m.ORDER_TIME_GTC = 1
    m.TRADE_ACTION_SLTP = 6
    # Filling type constants (ORDER_FILLING_* used in order request)
    m.ORDER_FILLING_FOK = 0
    m.ORDER_FILLING_IOC = 1
    m.ORDER_FILLING_RETURN = 2
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
    sym_info.filling_mode = 2  # IOC bit set (bit 1 = 2 means IOC supported)
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
        call_args = mock_mt5.order_send.call_args_list[0][0][0]
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
        call_args = mock_mt5.order_send.call_args_list[0][0][0]
        assert call_args["type"] == mock_mt5.ORDER_TYPE_SELL

    def test_returns_none_on_mt5_failure(self, mock_mt5):
        mock_mt5.order_send.return_value.retcode = 10004  # REQUOTE
        result = place_market_order("EURUSD", "LONG", 0.01, 1.09, 1.11, 10)
        assert result is None

    def test_sl_tp_rounded_to_digits(self, mock_mt5):
        place_market_order("EURUSD", "LONG", 0.01, 1.09551234, 1.10998765, 10)
        sltp_req = mock_mt5.order_send.call_args_list[1][0][0]
        assert sltp_req["sl"] == round(1.09551234, 5)
        assert sltp_req["tp"] == round(1.10998765, 5)


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


class TestSelectFillingType:
    """Tests for the private _select_filling_type() helper."""

    def test_ioc_preferred_when_supported(self, mock_mt5):
        """When both IOC and FOK are supported, prefer IOC."""
        from mt5.orders import _select_filling_type
        result = _select_filling_type(3)  # bits: IOC=1, FOK=1
        assert result == mock_mt5.ORDER_FILLING_IOC

    def test_ioc_used_when_only_ioc_supported(self, mock_mt5):
        """IOC only (bit 1 set, bit 0 clear)."""
        from mt5.orders import _select_filling_type
        result = _select_filling_type(2)  # bit 1 only
        assert result == mock_mt5.ORDER_FILLING_IOC

    def test_fok_used_when_only_fok_supported(self, mock_mt5):
        """FOK only (bit 0 set, bit 1 clear)."""
        from mt5.orders import _select_filling_type
        result = _select_filling_type(1)  # bit 0 only
        assert result == mock_mt5.ORDER_FILLING_FOK

    def test_return_used_as_fallback(self, mock_mt5):
        """Neither FOK nor IOC → RETURN as fallback."""
        from mt5.orders import _select_filling_type
        result = _select_filling_type(0)
        assert result == mock_mt5.ORDER_FILLING_RETURN


class TestFillingModeIntegration:
    """Verify place_market_order and close_position use the broker-selected filling type."""

    def test_place_order_uses_ioc_when_broker_supports_ioc(self, mock_mt5):
        mock_mt5.symbol_info.return_value.filling_mode = 2  # IOC supported
        place_market_order("EURUSD", "LONG", 0.01, 1.09, 1.11, 10)
        call_args = mock_mt5.order_send.call_args_list[0][0][0]
        assert call_args["type_filling"] == mock_mt5.ORDER_FILLING_IOC

    def test_place_order_uses_fok_when_only_fok_supported(self, mock_mt5):
        mock_mt5.symbol_info.return_value.filling_mode = 1  # FOK only
        place_market_order("EURUSD", "LONG", 0.01, 1.09, 1.11, 10)
        call_args = mock_mt5.order_send.call_args_list[0][0][0]
        assert call_args["type_filling"] == mock_mt5.ORDER_FILLING_FOK

    def test_place_order_uses_return_when_neither_supported(self, mock_mt5):
        mock_mt5.symbol_info.return_value.filling_mode = 0
        place_market_order("EURUSD", "LONG", 0.01, 1.09, 1.11, 10)
        call_args = mock_mt5.order_send.call_args_list[0][0][0]
        assert call_args["type_filling"] == mock_mt5.ORDER_FILLING_RETURN

    def test_close_position_uses_broker_filling_mode(self, mock_mt5):
        mock_mt5.symbol_info.return_value.filling_mode = 1  # FOK only
        close_position(ticket=111, symbol="EURUSD", lot=0.01, direction="LONG")
        call_args = mock_mt5.order_send.call_args[0][0]
        assert call_args["type_filling"] == mock_mt5.ORDER_FILLING_FOK


class TestSetPositionSltp:
    """Tests for set_position_sltp() — modify SL/TP on an open position."""

    def test_returns_true_on_success(self, mock_mt5):
        result = set_position_sltp(111222, "EURUSD", 1.09, 1.11)
        assert result is True

    def test_sends_trade_action_sltp(self, mock_mt5):
        set_position_sltp(111222, "EURUSD", 1.09, 1.11)
        call = mock_mt5.order_send.call_args[0][0]
        assert call["action"] == mock_mt5.TRADE_ACTION_SLTP

    def test_sets_correct_ticket_and_symbol(self, mock_mt5):
        set_position_sltp(111222, "EURUSD", 1.09, 1.11)
        call = mock_mt5.order_send.call_args[0][0]
        assert call["position"] == 111222
        assert call["symbol"] == "EURUSD"

    def test_rounds_sl_tp_to_digits(self, mock_mt5):
        set_position_sltp(111222, "EURUSD", 1.09551234, 1.10998765)
        call = mock_mt5.order_send.call_args[0][0]
        assert call["sl"] == round(1.09551234, 5)
        assert call["tp"] == round(1.10998765, 5)

    def test_returns_false_on_failure(self, mock_mt5):
        mock_mt5.order_send.return_value.retcode = 10004
        assert set_position_sltp(111222, "EURUSD", 1.09, 1.11) is False

    def test_returns_false_when_mt5_unavailable(self, mocker):
        from mt5 import orders as orders_module
        mocker.patch.object(orders_module, "mt5", None)
        assert set_position_sltp(111222, "EURUSD", 1.09, 1.11) is False

    def test_returns_false_when_symbol_info_unavailable(self, mock_mt5):
        mock_mt5.symbol_info.return_value = None
        assert set_position_sltp(111222, "EURUSD", 1.09, 1.11) is False


class TestPlaceMarketOrderPostFillSltp:
    """Verify place_market_order uses two-call: order without SL/TP, then TRADE_ACTION_SLTP."""

    def test_order_request_has_no_sl_tp(self, mock_mt5):
        """Initial order must NOT contain sl or tp."""
        place_market_order("EURUSD", "LONG", 0.01, 1.09, 1.11, 10)
        order_req = mock_mt5.order_send.call_args_list[0][0][0]
        assert "sl" not in order_req
        assert "tp" not in order_req

    def test_second_call_is_sltp(self, mock_mt5):
        """After the order fills, a TRADE_ACTION_SLTP request is sent."""
        place_market_order("EURUSD", "LONG", 0.01, 1.09, 1.11, 10)
        assert mock_mt5.order_send.call_count == 2
        sltp_req = mock_mt5.order_send.call_args_list[1][0][0]
        assert sltp_req["action"] == mock_mt5.TRADE_ACTION_SLTP
        assert sltp_req["position"] == 111222
        assert sltp_req["sl"] == round(1.09, 5)
        assert sltp_req["tp"] == round(1.11, 5)

    def test_returns_ticket_even_if_sltp_fails(self, mock_mt5):
        """Order ticket returned even when the SLTP follow-up fails."""
        success = MagicMock()
        success.retcode = 10009
        success.order = 111222
        failure = MagicMock()
        failure.retcode = 10004
        mock_mt5.order_send.side_effect = [success, failure]
        result = place_market_order("EURUSD", "LONG", 0.01, 1.09, 1.11, 10)
        assert result == 111222


class TestGetDailyDeals:
    def test_returns_closed_deals(self, mock_mt5):
        """Returns OUT deals (closing transactions) with profit."""
        deal = MagicMock()
        deal.ticket = 77
        deal.symbol = "EURUSD"
        deal.type = 0   # BUY close
        deal.entry = 1  # DEAL_ENTRY_OUT
        deal.profit = 45.50
        deal.volume = 0.01
        mock_mt5.history_deals_get.return_value = [deal]

        from datetime import datetime, timezone
        results = get_daily_deals(datetime(2026, 4, 30, tzinfo=timezone.utc))

        assert len(results) == 1
        assert results[0]["ticket"] == 77
        assert results[0]["profit"] == 45.50
        assert results[0]["type"] == "BUY"

    def test_excludes_entry_deals(self, mock_mt5):
        """Entry deals (DEAL_ENTRY_IN=0) are not returned."""
        deal = MagicMock()
        deal.ticket = 88
        deal.symbol = "EURUSD"
        deal.type = 0
        deal.entry = 0  # DEAL_ENTRY_IN — opening deal
        deal.profit = 0.0
        deal.volume = 0.01
        mock_mt5.history_deals_get.return_value = [deal]

        from datetime import datetime, timezone
        results = get_daily_deals(datetime(2026, 4, 30, tzinfo=timezone.utc))

        assert results == []

    def test_returns_empty_when_no_deals(self, mock_mt5):
        mock_mt5.history_deals_get.return_value = []
        from datetime import datetime, timezone
        assert get_daily_deals(datetime(2026, 4, 30, tzinfo=timezone.utc)) == []

    def test_returns_empty_when_mt5_none(self, mocker):
        mocker.patch("mt5.orders.mt5", None)
        from datetime import datetime, timezone
        assert get_daily_deals(datetime(2026, 4, 30, tzinfo=timezone.utc)) == []
