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
        "sl": round(sl, digits),
        "tp": round(tp, digits),
        "deviation": deviation,
        "magic": 20260425,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
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
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != RETCODE_DONE:
        retcode = result.retcode if result else "no result"
        logger.error("Failed to close position %d: retcode %s", ticket, retcode)
        return False

    logger.info("Closed position %d for %s", ticket, symbol)
    return True
