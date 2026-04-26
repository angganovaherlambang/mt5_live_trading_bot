"""
Main monitoring loop: fetches data, runs indicators and state machine per symbol,
enqueues GUI update dicts.

No tkinter dependency — communicates via a standard queue.Queue.

CONTRACT: Symbols are processed sequentially (one at a time). The PhaseState
objects are mutated in-place by advance_state — do not share state objects
across threads.
"""
from __future__ import annotations
import logging
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.indicators import calculate_indicators
from core.state import PhaseState, Phase
from core.state_machine import advance_state
from core.persistence import save_states, load_states

logger = logging.getLogger(__name__)

CANDLE_SECONDS = 300  # M5 = 5-minute bars
STATE_FILE = Path("strategy_state.json")


class MonitorLoop:
    """
    Runs in a background thread. Each M5 candle close:
      1. Fetches OHLCV for each symbol
      2. Calculates indicators
      3. Advances the state machine
      4. Enqueues a dict for the GUI thread to display

    Parameters
    ----------
    connection : mt5.connection.MT5Connection
    configs : dict[symbol, config_dict]
    symbols : list[str]
    update_queue : queue.Queue — GUI reads from this
    state_file : Path — where to persist PhaseState between restarts
    order_executor : OrderExecutor, optional — if provided, called after advance_state(); resets state
    """

    def __init__(
        self,
        connection,
        configs: dict,
        symbols: list[str],
        update_queue: queue.Queue,
        state_file: Path = STATE_FILE,
        order_executor=None,
    ) -> None:
        self.connection = connection
        self.configs = configs
        self.symbols = symbols
        self.update_queue = update_queue
        self.state_file = state_file
        self.order_executor = order_executor
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Load persisted states or start fresh
        loaded = load_states(state_file, max_age_seconds=1800)
        self.states: dict[str, PhaseState] = {
            sym: loaded.get(sym, PhaseState(symbol=sym)) for sym in symbols
        }

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="MonitorLoop")
        self._thread.start()
        logger.info("MonitorLoop started for %d symbols", len(self.symbols))

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        save_states(self.states, self.state_file)
        logger.info("MonitorLoop stopped, state saved")

    def _run(self) -> None:
        while self._running:
            now = datetime.now(tz=timezone.utc)
            if self._is_candle_close(now):
                self._tick()
            time.sleep(1)

    def _is_candle_close(self, now: datetime) -> bool:
        """True once per M5 boundary (second 0 or 1)."""
        return (now.minute % 5 == 0) and (now.second <= 1)

    def _tick(self) -> None:
        """Process all symbols on a candle close."""
        for symbol in self.symbols:
            if not self._running:
                break
            try:
                self._process_symbol(symbol)
            except Exception as exc:
                logger.exception("Error processing %s: %s", symbol, exc)
        save_states(self.states, self.state_file)

    def _process_symbol(self, symbol: str) -> None:
        config = self.configs.get(symbol)
        if not config:
            return

        df = self.connection.fetch_ohlcv(symbol, timeframe=16385, count=151)  # 16385 = M5
        if df is None or len(df) < 50:
            logger.warning("%s: insufficient data, skipping", symbol)
            return

        indicators = calculate_indicators(df, config)
        state = self.states[symbol]

        # IN_TRADE: skip scan/advance, just check whether position is still open
        if state.phase == Phase.IN_TRADE:
            if self.order_executor is not None:
                self.order_executor.check_in_trade(symbol, state)
            self.update_queue.put({
                "symbol": symbol,
                "phase": state.phase.value,
                "direction": state.direction,
                "pullback_count": state.pullback_count,
                "window_open": state.window_open,
                "atr": indicators["atr"],
                "trend": indicators["trend"],
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            })
            return

        # Normal scan flow: advance state machine then attempt entry
        self.states[symbol] = advance_state(state, df, indicators, config, bar_index=-2)

        # execute() resets state to SCANNING on completion; update_queue reflects post-execution state
        if self.order_executor is not None:
            self.order_executor.execute(symbol, self.states[symbol], indicators)

        self.update_queue.put({
            "symbol": symbol,
            "phase": self.states[symbol].phase.value,
            "direction": self.states[symbol].direction,
            "pullback_count": self.states[symbol].pullback_count,
            "window_open": self.states[symbol].window_open,
            "atr": indicators["atr"],
            "trend": indicators["trend"],
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        })
