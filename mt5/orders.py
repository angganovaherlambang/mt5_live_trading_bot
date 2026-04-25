"""
Thin wrapper around the MetaTrader5 order API.

One function per operation. All MT5 calls are here — nothing else
in the codebase should import MetaTrader5 directly for order placement.
"""
from __future__ import annotations
import logging
from typing import Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

RETCODE_DONE = 10009  # MT5 success code

# Bitmask values for sym_info.filling_mode (which filling types the broker supports)
_SYMBOL_FILLING_FOK = 1  # bit 0: ORDER_FILLING_FOK supported
_SYMBOL_FILLING_IOC = 2  # bit 1: ORDER_FILLING_IOC supported


def _select_filling_type(filling_mode_bits: int) -> int:
    """
    Return the ORDER_FILLING_* constant best supported by this broker/symbol.

    Parameters
    ----------
    filling_mode_bits : int
        sym_info.filling_mode from MT5 — bitmask of supported types:
        bit 0 (value 1) = FOK supported
        bit 1 (value 2) = IOC supported

    Priority: IOC > FOK > RETURN.
    IOC allows partial cancellation and is widely supported.
    RETURN is the fallback for brokers/instruments with no explicit declaration.
    """
    if filling_mode_bits & _SYMBOL_FILLING_IOC:
        return mt5.ORDER_FILLING_IOC
    if filling_mode_bits & _SYMBOL_FILLING_FOK:
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN


def place_market_order(
    symbol: str,
    direction: str,
    lot: float,
    sl: float,
    tp: float,
    deviation: int = 10,
    comment: str = "sunrise",
) -> Optional[int]:
    """
    Place a market order immediately.

    Returns the order ticket (int) on success, None on failure.

    Parameters
    ----------
    symbol    : e.g. "EURUSD"
    direction : "LONG" or "SHORT"
    lot       : lot size (already validated by risk.py)
    sl        : stop-loss price
    tp        : take-profit price
    deviation : max slippage in points (default 10 = 1 pip for 5-digit brokers)
    comment   : order comment shown in MT5 terminal
    """
    if mt5 is None:
        logger.error("MetaTrader5 not available")
        return None

    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        logger.error("Cannot get symbol info for %s", symbol)
        return None

    digits = sym_info.digits
    filling_type = _select_filling_type(sym_info.filling_mode)
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        logger.error("Cannot get tick for %s", symbol)
        return None

    if direction not in ("LONG", "SHORT"):
        logger.error("%s: invalid direction %r", symbol, direction)
        return None

    order_type = mt5.ORDER_TYPE_BUY if direction == "LONG" else mt5.ORDER_TYPE_SELL
    price = tick.ask if direction == "LONG" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": round(price, digits),
        "deviation": deviation,
        "magic": 20260425,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_type,
    }

    result = mt5.order_send(request)

    if result is None or result.retcode != RETCODE_DONE:
        retcode = result.retcode if result else "no result"
        logger.error(
            "%s: order_send failed — retcode %s (direction=%s, lot=%.2f, sl=%.5f, tp=%.5f)",
            symbol, retcode, direction, lot, sl, tp,
        )
        return None

    logger.info(
        "%s: order placed — ticket=%d direction=%s lot=%.2f sl=%.5f tp=%.5f",
        symbol, result.order, direction, lot, sl, tp,
    )

    if not set_position_sltp(result.order, symbol, sl, tp):
        logger.warning(
            "%s: order placed (ticket=%d) but SL/TP set failed — position open without SL/TP",
            symbol, result.order,
        )

    return result.order


def get_open_positions(symbol: str) -> list[dict]:
    """
    Return a list of open positions for `symbol`.
    Each dict has: ticket, symbol, type ("BUY"/"SELL"), volume, price_open, sl, tp.
    Returns [] if no positions or MT5 unavailable.
    """
    if mt5 is None:
        logger.warning("MetaTrader5 not available, cannot get positions for %s", symbol)
        return []

    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return []

    return [
        {
            "ticket": p.ticket,
            "symbol": p.symbol,
            "type": "BUY" if p.type == 0 else "SELL",
            "volume": p.volume,
            "price_open": p.price_open,
            "sl": p.sl,
            "tp": p.tp,
        }
        for p in positions
    ]


def set_position_sltp(ticket: int, symbol: str, sl: float, tp: float) -> bool:
    """
    Set stop-loss and take-profit on an already-open position.

    Sends a TRADE_ACTION_SLTP request — does not re-open or modify the order,
    only adjusts the stop levels on an existing position identified by ticket.

    Returns True on success, False on failure.
    """
    if mt5 is None:
        return False

    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        logger.error("Cannot get symbol info to set SL/TP for position %d", ticket)
        return False
    digits = sym_info.digits

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": symbol,
        "position": ticket,
        "sl": round(sl, digits),
        "tp": round(tp, digits),
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != RETCODE_DONE:
        retcode = result.retcode if result else "no result"
        logger.error("Failed to set SL/TP for position %d: retcode %s", ticket, retcode)
        return False

    logger.info("SL/TP set for position %d: sl=%.5f tp=%.5f", ticket, sl, tp)
    return True


def close_position(ticket: int, symbol: str, lot: float, direction: str) -> bool:
    """
    Close an open position by ticket.
    Returns True on success, False on failure.
    """
    if mt5 is None:
        return False

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        logger.error("Cannot get tick to close position %d", ticket)
        return False

    if direction not in ("LONG", "SHORT"):
        logger.error("%s: invalid direction %r for close", symbol, direction)
        return False

    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        logger.error("Cannot get symbol info to close position %d for %s", ticket, symbol)
        return False
    digits = sym_info.digits
    filling_type = _select_filling_type(sym_info.filling_mode)

    close_type = mt5.ORDER_TYPE_SELL if direction == "LONG" else mt5.ORDER_TYPE_BUY
    price = tick.bid if direction == "LONG" else tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": close_type,
        "position": ticket,
        "price": round(price, digits),
        "deviation": 10,
        "magic": 20260425,
        "comment": "sunrise_close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_type,
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != RETCODE_DONE:
        retcode = result.retcode if result else "no result"
        logger.error("Failed to close position %d: retcode %s", ticket, retcode)
        return False

    logger.info("Closed position %d for %s", ticket, symbol)
    return True


def get_symbol_info(symbol: str) -> Optional[dict]:
    """
    Return broker contract specs needed for position sizing.

    Returns None if MT5 unavailable or symbol not found.
    Keys: point, digits, trade_tick_value, trade_tick_size,
          trade_contract_size, volume_min, volume_max, volume_step.
    """
    if mt5 is None:
        logger.error("MetaTrader5 not available")
        return None

    info = mt5.symbol_info(symbol)
    if info is None:
        logger.error("Cannot get symbol info for %s", symbol)
        return None

    return {
        "point": info.point,
        "digits": info.digits,
        "trade_tick_value": info.trade_tick_value,
        "trade_tick_size": info.trade_tick_size,
        "trade_contract_size": info.trade_contract_size,
        "volume_min": info.volume_min,
        "volume_max": info.volume_max,
        "volume_step": info.volume_step,
    }


def get_current_price(symbol: str, direction: str) -> Optional[float]:
    """
    Return the expected fill price for a new market order.

    LONG  → ask (we buy at ask)
    SHORT → bid (we sell at bid)

    Returns None if MT5 unavailable, no tick available, or direction invalid.
    """
    if mt5 is None:
        logger.error("MetaTrader5 not available")
        return None

    if direction not in ("LONG", "SHORT"):
        logger.error("%s: invalid direction %r", symbol, direction)
        return None

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        logger.error("Cannot get tick for %s", symbol)
        return None

    return tick.ask if direction == "LONG" else tick.bid
