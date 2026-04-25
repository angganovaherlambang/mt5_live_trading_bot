"""
Pure SL/TP price-level calculation and lot-size math.

No MT5 API dependency — all inputs are plain Python scalars.
Called by monitor/trader.py before placing any order.
"""
from __future__ import annotations
import math


def calculate_sl_tp(
    direction: str,
    entry_price: float,
    atr: float,
    sl_multiplier: float,
    tp_multiplier: float,
) -> tuple[float, float]:
    """
    Return (stop_loss_price, take_profit_price) for an entry.

    For LONG:  SL = entry - atr * sl_multiplier
               TP = entry + atr * tp_multiplier
    For SHORT: SL = entry + atr * sl_multiplier
               TP = entry - atr * tp_multiplier
    """
    if direction not in ("LONG", "SHORT"):
        raise ValueError(f"direction must be 'LONG' or 'SHORT', got {direction!r}")

    sl_distance = atr * sl_multiplier
    tp_distance = atr * tp_multiplier

    if direction == "LONG":
        return entry_price - sl_distance, entry_price + tp_distance
    else:  # SHORT
        return entry_price + sl_distance, entry_price - tp_distance


def calculate_lot_size(
    risk_amount: float,
    sl_pips: float,
    pip_value_per_lot: float,
    min_lot: float,
    max_lot: float,
    lot_step: float,
) -> float:
    """
    Return the lot size that risks exactly `risk_amount` given a `sl_pips` stop.

    Parameters
    ----------
    risk_amount      : dollar amount to risk (e.g. account_balance * 0.01 for 1%)
    sl_pips          : stop-loss distance in pips (entry to SL)
    pip_value_per_lot: dollar value of 1 pip for 1 standard lot
    min_lot          : broker minimum lot (e.g. 0.01)
    max_lot          : hard cap (e.g. 0.5 for safety)
    lot_step         : broker lot step (e.g. 0.01)
    """
    if risk_amount <= 0 or sl_pips <= 0 or pip_value_per_lot <= 0:
        return min_lot

    raw = risk_amount / (sl_pips * pip_value_per_lot)

    # Round down to nearest lot_step
    steps = math.floor(raw / lot_step)
    lot = steps * lot_step

    return max(min_lot, min(lot, max_lot))


def calculate_lot_size_from_point_value(
    risk_amount: float,
    sl_distance: float,
    value_per_point: float,
    point_size: float,
    min_lot: float,
    max_lot: float,
    lot_step: float,
) -> float:
    """
    Return the lot size that risks exactly `risk_amount`, using MT5 broker specs.

    This is the correct formula for all instruments — handles forex, gold,
    silver, indices, and other non-standard contract sizes.

    Parameters
    ----------
    risk_amount    : account currency to risk (e.g. balance * 0.01 for 1%)
    sl_distance    : SL distance in price units (abs(entry_price - sl_price))
    value_per_point: account currency per 1-point move per 1 lot.
                     Derive from MT5: trade_tick_value / trade_tick_size * point
                     EURUSD example: $10 / 0.00001 × 0.00001 = $10/point/lot
                     XAUUSD example: $1  / 0.01    × 0.01    = $1/point/lot
    point_size     : size of 1 price point = symbol_info.point
    min_lot        : broker minimum lot (e.g. 0.01)
    max_lot        : hard cap (e.g. 0.5 for safety)
    lot_step       : broker lot step (e.g. 0.01)
    """
    if risk_amount <= 0 or sl_distance <= 0 or value_per_point <= 0 or point_size <= 0:
        return min_lot

    sl_points = sl_distance / point_size
    raw = risk_amount / (sl_points * value_per_point)

    steps = math.floor(raw / lot_step)
    lot = steps * lot_step

    return max(min_lot, min(lot, max_lot))
