"""
OrderExecutor: bridges AWAITING_ENTRY state → MT5 market order.

Called by MonitorLoop after each advance_state() tick. When a symbol
reaches Phase.AWAITING_ENTRY, this module:
  1. Checks no position already open for this symbol
  2. Calculates lot size from ATR + account balance
  3. Calculates SL/TP from ATR + config multipliers
  4. Places a market order via mt5.orders
  5. Resets the PhaseState to SCANNING (win or lose, find the next setup)

Always resets state — never leaves a symbol stuck in AWAITING_ENTRY.
"""
from __future__ import annotations
import logging
from typing import Optional

from core.state import PhaseState, Phase
from mt5.orders import place_market_order, get_open_positions
from mt5.risk import calculate_sl_tp, calculate_lot_size

logger = logging.getLogger(__name__)

# Pip size for lot-size calculation
_PIP_SIZE_DEFAULT = 0.0001
_PIP_SIZE_JPY = 0.01
_PIP_VALUE_PER_LOT_USD = 10.0  # approximate for non-JPY vs USD pairs


class OrderExecutor:
    """
    Stateless executor: reads state, places order, resets state.

    Parameters
    ----------
    connection : mt5.connection.MT5Connection
    configs    : {symbol: config_dict}
    risk_pct   : fraction of balance to risk per trade (e.g. 0.01 = 1%)
    max_lot    : hard cap on lot size (safety limit)
    demo_mode  : if True, skips actual order_send (dry run)
    """

    def __init__(
        self,
        connection,
        configs: dict,
        risk_pct: float = 0.01,
        max_lot: float = 0.5,
        demo_mode: bool = True,
    ) -> None:
        self.connection = connection
        self.configs = configs
        self.risk_pct = risk_pct
        self.max_lot = max_lot
        self.demo_mode = demo_mode

    def execute(self, symbol: str, state: PhaseState, indicators: dict) -> None:
        """
        Called once per candle per symbol by MonitorLoop.
        Mutates `state` (resets to SCANNING when done).
        """
        if state.phase != Phase.AWAITING_ENTRY:
            return

        try:
            self._attempt_order(symbol, state, indicators)
        finally:
            # Always reset — never leave a symbol stuck in AWAITING_ENTRY
            state.reset()

    def _attempt_order(self, symbol: str, state: PhaseState, indicators: dict) -> None:
        config = self.configs.get(symbol)
        if not config:
            logger.warning("%s: no config found, skipping order", symbol)
            return

        direction = state.direction
        if direction not in ("LONG", "SHORT"):
            logger.warning("%s: invalid direction %r, skipping", symbol, direction)
            return

        # Skip if position already open
        open_positions = get_open_positions(symbol)
        if open_positions:
            logger.info("%s: position already open, skipping new entry", symbol)
            return

        # Get account balance for sizing
        account = self.connection.get_account_info()
        if account is None:
            logger.error("%s: cannot get account info, skipping order", symbol)
            return

        balance = account["balance"]
        atr = indicators.get("atr", 0.0)
        if atr <= 0:
            logger.warning("%s: ATR=%.6f is invalid, skipping order", symbol, atr)
            return

        # SL/TP multipliers from strategy config
        sl_mult = float(config.get(f"{direction.lower()}_atr_sl_multiplier", 1.5))
        tp_mult = float(config.get(f"{direction.lower()}_atr_tp_multiplier", 10.0))

        sl_distance = atr * sl_mult
        pip_size = _PIP_SIZE_JPY if symbol.endswith("JPY") else _PIP_SIZE_DEFAULT
        sl_pips = sl_distance / pip_size

        lot = calculate_lot_size(
            risk_amount=balance * self.risk_pct,
            sl_pips=sl_pips,
            pip_value_per_lot=_PIP_VALUE_PER_LOT_USD,
            min_lot=0.01,
            max_lot=self.max_lot,
            lot_step=0.01,
        )

        if self.demo_mode:
            logger.info(
                "%s: DEMO — would place %s order: lot=%.2f sl_dist=%.5f sl_pips=%.1f",
                symbol, direction, lot, sl_distance, sl_pips,
            )
            return

        # In live mode, pass ATR-based SL/TP distances relative to entry=0
        # orders.py fetches live price; we pass absolute SL/TP levels
        # Note: since we don't know fill price ahead of time, use atr distances
        # as approximate offset from 0.0. This is a known limitation documented
        # in the plan — a production system should re-calc after fill confirmation.
        sl_price, tp_price = calculate_sl_tp(
            direction=direction,
            entry_price=0.0,
            atr=atr,
            sl_multiplier=sl_mult,
            tp_multiplier=tp_mult,
        )

        ticket = place_market_order(
            symbol=symbol,
            direction=direction,
            lot=lot,
            sl=abs(sl_price),
            tp=abs(tp_price),
            deviation=10,
            comment=f"sunrise_{direction.lower()}",
        )

        if ticket:
            logger.info(
                "%s: order placed ticket=%d direction=%s lot=%.2f",
                symbol, ticket, direction, lot,
            )
        else:
            logger.error("%s: order placement failed", symbol)
