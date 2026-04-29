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
  7. On success: transitions state to IN_TRADE with the order ticket.
     On failure or demo mode: resets state to SCANNING.
"""
from __future__ import annotations
import logging
from typing import Optional

from core.state import PhaseState, Phase
from mt5.orders import (
    place_market_order,
    get_open_positions,
    get_symbol_info,
    get_current_price,
    set_position_sltp,
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
    notifier   : optional TelegramNotifier — sends alerts on trade events
    """

    def __init__(
        self,
        connection,
        configs: dict,
        risk_pct: float = 0.01,
        max_lot: float = 0.5,
        demo_mode: bool = True,
        notifier=None,
    ) -> None:
        self.connection = connection
        self.configs = configs
        self.risk_pct = risk_pct
        self.max_lot = max_lot
        self.demo_mode = demo_mode
        self.notifier = notifier

    def execute(self, symbol: str, state: PhaseState, indicators: dict) -> None:
        """
        Called once per candle per symbol by MonitorLoop.
        On success: transitions state to IN_TRADE with the order ticket.
        On failure or demo mode: resets state to SCANNING.
        """
        if state.phase != Phase.AWAITING_ENTRY:
            return

        ticket = self._attempt_order(symbol, state, indicators)
        if ticket:
            state.phase = Phase.IN_TRADE
            state.active_ticket = ticket
        else:
            state.reset()

    def check_in_trade(self, symbol: str, state: PhaseState) -> None:
        """
        Called each candle when phase == IN_TRADE.
        Resets to SCANNING when the active position is no longer open.
        """
        if state.phase != Phase.IN_TRADE:
            return
        positions = get_open_positions(symbol)
        active_tickets = {p["ticket"] for p in positions}
        if state.active_ticket not in active_tickets:
            logger.info(
                "%s: position %d closed (SL/TP or manual), resetting to SCANNING",
                symbol, state.active_ticket,
            )
            if self.notifier:
                self.notifier.notify_position_closed(symbol, state.direction, state.active_ticket)
            state.reset()

    def update_trailing_stop(self, symbol: str, state: PhaseState, indicators: dict) -> None:
        """
        Tighten SL toward the current price each candle while in-trade.

        Computes candidate SL = current_price ∓ atr × sl_multiplier and calls
        set_position_sltp() only when the candidate is strictly better than the
        current SL — never widens the stop.

        LONG : SL moves up   (candidate > current_sl)
        SHORT: SL moves down (candidate < current_sl)
        """
        if state.phase != Phase.IN_TRADE:
            return

        atr = indicators.get("atr", 0.0)
        if atr <= 0:
            return

        direction = state.direction
        if direction not in ("LONG", "SHORT"):
            return

        positions = get_open_positions(symbol)
        position = next((p for p in positions if p["ticket"] == state.active_ticket), None)
        if position is None:
            return

        current_price = get_current_price(symbol, direction)
        if current_price is None:
            return

        config = self.configs.get(symbol, {})
        sl_mult = float(config.get(f"{direction.lower()}_atr_sl_multiplier", 1.5))
        current_sl = position["sl"]
        current_tp = position["tp"]

        if direction == "LONG":
            candidate_sl = current_price - atr * sl_mult
            should_move = candidate_sl > current_sl
        else:
            candidate_sl = current_price + atr * sl_mult
            should_move = candidate_sl < current_sl

        if should_move:
            logger.info(
                "%s: trailing stop %s SL %.5f → %.5f",
                symbol, direction, current_sl, candidate_sl,
            )
            set_position_sltp(state.active_ticket, symbol, candidate_sl, current_tp)
            if self.notifier:
                self.notifier.notify_sl_moved(symbol, direction, current_sl, candidate_sl)

    def _attempt_order(self, symbol: str, state: PhaseState, indicators: dict) -> Optional[int]:
        """
        Try to place a market order. Returns the ticket int on success, None otherwise.
        """
        config = self.configs.get(symbol)
        if not config:
            logger.warning("%s: no config found, skipping order", symbol)
            return

        direction = state.direction
        if direction not in ("LONG", "SHORT"):
            logger.warning("%s: invalid direction %r, skipping", symbol, direction)
            return None

        atr = indicators.get("atr", 0.0)
        if atr <= 0:
            logger.warning("%s: ATR=%.6f is invalid, skipping order", symbol, atr)
            return None

        # Skip if position already open for this symbol
        open_positions = get_open_positions(symbol)
        if open_positions:
            logger.info("%s: position already open, skipping new entry", symbol)
            return None

        # Account balance for risk sizing
        account = self.connection.get_account_info()
        if account is None:
            logger.error("%s: cannot get account info, skipping order", symbol)
            return None

        balance = account["balance"]

        # Broker contract specs — needed for accurate lot sizing
        sym_info = get_symbol_info(symbol)
        if sym_info is None:
            logger.error("%s: cannot get symbol info, skipping order", symbol)
            return None

        # Current bid/ask — used as expected entry price for SL/TP calculation
        entry_price = get_current_price(symbol, direction)
        if entry_price is None:
            logger.error("%s: cannot get current price, skipping order", symbol)
            return None

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
        if tick_size <= 0:
            logger.error("%s: broker returned invalid tick_size=%.8f, skipping order", symbol, tick_size)
            return None
        value_per_point = tick_value / tick_size * point

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
            return None

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
            if self.notifier:
                self.notifier.notify_order_placed(
                    symbol, direction, lot, entry_price, sl_price, tp_price, ticket
                )
        else:
            logger.error("%s: order placement failed", symbol)
        return ticket
