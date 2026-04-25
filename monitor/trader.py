"""
OrderExecutor: bridges AWAITING_ENTRY state → MT5 market order.

Called by MonitorLoop after each advance_state() tick. When a symbol
reaches Phase.AWAITING_ENTRY, this module:
  1. Checks no position already open for this symbol
  2. Fetches current bid/ask price as the expected entry price
  3. Fetches broker contract specs (point, tick_value, contract_size, lot limits)
  4. Calculates SL/TP absolute levels from entry price + ATR multipliers
  5. Calculates lot size using the MT5-native value_per_point formula
  6. Places a market order via mt5.orders (live) or logs intent (demo)
  7. Resets the PhaseState to SCANNING — never leaves a symbol stuck in AWAITING_ENTRY

Always resets state — never leaves a symbol stuck in AWAITING_ENTRY.
"""
from __future__ import annotations
import logging

from core.state import PhaseState, Phase
from mt5.orders import (
    place_market_order,
    get_open_positions,
    get_symbol_info,
    get_current_price,
)
from mt5.risk import calculate_sl_tp, calculate_lot_size_from_point_value

logger = logging.getLogger(__name__)


class OrderExecutor:
    """
    Stateless executor: reads state, places order, resets state.

    Parameters
    ----------
    connection : mt5.connection.MT5Connection
    configs    : {symbol: config_dict}
    risk_pct   : fraction of balance to risk per trade (e.g. 0.01 = 1%)
    max_lot    : hard cap on lot size (safety limit)
    demo_mode  : if True, logs what it would do but never calls place_market_order
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

        # Skip if position already open for this symbol
        open_positions = get_open_positions(symbol)
        if open_positions:
            logger.info("%s: position already open, skipping new entry", symbol)
            return

        # Account balance for risk sizing
        account = self.connection.get_account_info()
        if account is None:
            logger.error("%s: cannot get account info, skipping order", symbol)
            return

        balance = account["balance"]
        atr = indicators.get("atr", 0.0)
        if atr <= 0:
            logger.warning("%s: ATR=%.6f is invalid, skipping order", symbol, atr)
            return

        # Broker contract specs — needed for accurate lot sizing
        sym_info = get_symbol_info(symbol)
        if sym_info is None:
            logger.error("%s: cannot get symbol info, skipping order", symbol)
            return

        # Current bid/ask — used as expected entry price for SL/TP calculation
        entry_price = get_current_price(symbol, direction)
        if entry_price is None:
            logger.error("%s: cannot get current price, skipping order", symbol)
            return

        # SL/TP multipliers from strategy config
        sl_mult = float(config.get(f"{direction.lower()}_atr_sl_multiplier", 1.5))
        tp_mult = float(config.get(f"{direction.lower()}_atr_tp_multiplier", 10.0))

        # Absolute SL/TP price levels (based on current ask/bid as entry estimate)
        sl_price, tp_price = calculate_sl_tp(
            direction=direction,
            entry_price=entry_price,
            atr=atr,
            sl_multiplier=sl_mult,
            tp_multiplier=tp_mult,
        )
        sl_distance = atr * sl_mult

        # value_per_point: correct for all instruments (forex, gold, silver, etc.)
        # Formula from MT5 docs: trade_tick_value / trade_tick_size * point
        tick_value = sym_info["trade_tick_value"]
        tick_size = sym_info["trade_tick_size"]
        point = sym_info["point"]
        value_per_point = (tick_value / tick_size * point) if tick_size > 0 else tick_value

        lot = calculate_lot_size_from_point_value(
            risk_amount=balance * self.risk_pct,
            sl_distance=sl_distance,
            value_per_point=value_per_point,
            point_size=point,
            min_lot=sym_info["volume_min"],
            max_lot=min(self.max_lot, sym_info["volume_max"]),
            lot_step=sym_info["volume_step"],
        )

        if self.demo_mode:
            logger.info(
                "%s: DEMO — would place %s order: entry=%.5f sl=%.5f tp=%.5f lot=%.2f",
                symbol, direction, entry_price, sl_price, tp_price, lot,
            )
            return

        ticket = place_market_order(
            symbol=symbol,
            direction=direction,
            lot=lot,
            sl=sl_price,
            tp=tp_price,
            deviation=10,
            comment=f"sunrise_{direction.lower()}",
        )

        if ticket:
            logger.info(
                "%s: order placed ticket=%d direction=%s lot=%.2f sl=%.5f tp=%.5f",
                symbol, ticket, direction, lot, sl_price, tp_price,
            )
        else:
            logger.error("%s: order placement failed", symbol)
