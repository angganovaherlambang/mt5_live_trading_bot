"""
Telegram notification sender.

Sends trade alerts and error notifications via Telegram Bot API.
All methods are fire-and-forget — never raise, never block the trading loop.

Configure via env vars:
  TELEGRAM_BOT_TOKEN  — from @BotFather
  TELEGRAM_CHAT_ID    — your personal or group chat ID
"""
from __future__ import annotations
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, timeout: float = 5.0) -> None:
        self._url = _API_URL.format(token=token)
        self._chat_id = str(chat_id)
        self._timeout = timeout

    def send(self, message: str) -> bool:
        """POST message to Telegram. Returns True on success, False on any failure."""
        try:
            resp = requests.post(
                self._url,
                json={"chat_id": self._chat_id, "text": message},
                timeout=self._timeout,
            )
            if resp.status_code != 200:
                logger.warning("Telegram send failed: HTTP %d", resp.status_code)
                return False
            return True
        except Exception as exc:
            logger.warning("Telegram send error: %s", exc)
            return False

    def notify_order_placed(
        self,
        symbol: str,
        direction: str,
        lot: float,
        entry: float,
        sl: float,
        tp: float,
        ticket: int,
    ) -> None:
        arrow = "🟢" if direction == "LONG" else "🔴"
        self.send(
            f"{arrow} ORDER PLACED\n"
            f"{direction} {symbol} | Lot: {lot:.2f} | Ticket: #{ticket}\n"
            f"Entry: {entry:.5f} | SL: {sl:.5f} | TP: {tp:.5f}"
        )

    def notify_position_closed(self, symbol: str, direction: str, ticket: int) -> None:
        self.send(f"⚫ CLOSED {direction} {symbol} | Ticket: #{ticket}")

    def notify_sl_moved(
        self, symbol: str, direction: str, old_sl: float, new_sl: float
    ) -> None:
        arrow = "↑" if direction == "LONG" else "↓"
        self.send(
            f"📈 TRAILING STOP {symbol} {direction}\n"
            f"SL {arrow} {old_sl:.5f} → {new_sl:.5f}"
        )

    def notify_error(self, context: Optional[str], message: str) -> None:
        prefix = f"[{context}] " if context else ""
        self.send(f"⚠️ ERROR {prefix}{message}")
