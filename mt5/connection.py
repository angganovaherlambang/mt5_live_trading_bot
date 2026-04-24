"""
MetaTrader 5 connection management.

Wraps the MetaTrader5 Python API with reconnection logic and a clean interface.
The rest of the codebase should depend on this class, not on MetaTrader5 directly.
"""
from __future__ import annotations
import logging
import time
from typing import Optional

try:
    import MetaTrader5 as mt5
except ImportError:  # Allow import on non-Windows / CI machines
    mt5 = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

MAX_RECONNECT_ATTEMPTS = 3
RECONNECT_BASE_DELAY = 5.0  # seconds


class MT5Connection:
    def __init__(self) -> None:
        self._is_connected: bool = False
        self.reconnect_attempts: int = 0

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def connect(self) -> bool:
        """Initialise MT5. Returns True on success."""
        if mt5 is None:
            logger.error("MetaTrader5 package not available")
            return False
        if mt5.initialize():
            self._is_connected = True
            self.reconnect_attempts = 0
            logger.info("MT5 connected. Account: %s", self._account_login())
            return True
        logger.error("MT5 initialize() failed: %s", mt5.last_error())
        return False

    def disconnect(self) -> None:
        if mt5 is not None:
            mt5.shutdown()
        self._is_connected = False
        logger.info("MT5 disconnected")

    def reconnect(self) -> bool:
        """Attempt reconnection with exponential backoff. Returns True on success."""
        if self.reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
            logger.error("Max reconnect attempts (%d) reached", MAX_RECONNECT_ATTEMPTS)
            return False
        delay = RECONNECT_BASE_DELAY * (2 ** self.reconnect_attempts)
        logger.warning("Reconnecting in %.1fs (attempt %d)", delay, self.reconnect_attempts + 1)
        time.sleep(delay)
        self.reconnect_attempts += 1
        # Try to reconnect; preserve reconnect_attempts counter
        if mt5 is None:
            logger.error("MetaTrader5 package not available")
            return False
        if mt5.initialize():
            self._is_connected = True
            logger.info("MT5 reconnected. Account: %s", self._account_login())
            return True
        logger.error("MT5 initialize() failed: %s", mt5.last_error())
        return False

    def get_account_info(self) -> Optional[dict]:
        if not self._is_connected or mt5 is None:
            return None
        info = mt5.account_info()
        if info is None:
            return None
        return {
            "balance": info.balance,
            "equity": info.equity,
            "login": info.login,
        }

    def fetch_ohlcv(self, symbol: str, timeframe, count: int = 151):
        """Fetch OHLCV bars. Returns a pandas DataFrame or None."""
        if not self._is_connected or mt5 is None:
            return None
        import pandas as pd
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None or len(rates) == 0:
            logger.warning("No data for %s", symbol)
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    def _account_login(self) -> str:
        info = self.get_account_info()
        return str(info["login"]) if info else "unknown"
