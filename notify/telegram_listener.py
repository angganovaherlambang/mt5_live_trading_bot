"""
Telegram command listener.

Polls getUpdates in a background thread and responds to commands.
Only processes messages from the configured chat_id.

Supported commands:
  /status    — current phase of all monitored symbols
  /positions — open trades with unrealized P&L
  /balance   — account balance + equity
  /help      — list all commands

Configure via the same env vars as TelegramNotifier:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
"""
from __future__ import annotations
import logging
import threading
import time
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)

_PHASE_ICONS = {
    "SCANNING": "🔍",
    "ARMED": "⚡",
    "WINDOW_OPEN": "🪟",
    "AWAITING_ENTRY": "⏳",
    "IN_TRADE": "🔴",
}

_HELP_TEXT = (
    "📖 Available commands:\n"
    "/status    — phase of all 8 symbols\n"
    "/positions — open trades + unrealized P&L\n"
    "/balance   — account balance + equity\n"
    "/help      — this message"
)


class TelegramListener:
    """
    Background polling listener for Telegram bot commands.

    Parameters
    ----------
    token           : Telegram bot token (from @BotFather)
    chat_id         : Only process messages from this chat ID
    get_status      : Callable → {symbol: {phase, direction, ticket}}
    get_positions   : Callable → list of open position dicts (with profit field)
    get_balance     : Callable → {balance, equity, login} or None
    poll_timeout    : Long-poll timeout in seconds (Telegram holds the connection)
    request_timeout : requests timeout (must be > poll_timeout)
    """

    def __init__(
        self,
        token: str,
        chat_id: str,
        get_status: Callable[[], dict],
        get_positions: Optional[Callable[[], list]] = None,
        get_balance: Optional[Callable[[], Optional[dict]]] = None,
        poll_timeout: int = 30,
        request_timeout: float = 35.0,
    ) -> None:
        self._base = f"https://api.telegram.org/bot{token}"
        self._chat_id = str(chat_id)
        self._get_status = get_status
        self._get_positions = get_positions or (lambda: [])
        self._get_balance = get_balance or (lambda: None)
        self._poll_timeout = poll_timeout
        self._request_timeout = request_timeout
        self._offset = 0
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="TelegramListener"
        )
        self._thread.start()
        logger.info("TelegramListener started")

    def stop(self) -> None:
        self._running = False
        logger.info("TelegramListener stopped")

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _poll_loop(self) -> None:
        while self._running:
            try:
                updates = self._fetch_updates()
                for update in updates:
                    self._offset = update["update_id"] + 1
                    self._handle(update)
            except Exception as exc:
                logger.warning("TelegramListener poll error: %s", exc)
                time.sleep(5)

    def _fetch_updates(self) -> list[dict]:
        resp = requests.get(
            f"{self._base}/getUpdates",
            params={
                "offset": self._offset,
                "timeout": self._poll_timeout,
                "allowed_updates": ["message"],
            },
            timeout=self._request_timeout,
        )
        if resp.status_code != 200:
            return []
        return resp.json().get("result", [])

    def _handle(self, update: dict) -> None:
        msg = update.get("message") or {}
        text = (msg.get("text") or "").strip()
        chat_id = str((msg.get("chat") or {}).get("id", ""))
        if chat_id != self._chat_id:
            return
        _DISPATCH = {
            "/status": self._reply_status,
            "/positions": self._reply_positions,
            "/balance": self._reply_balance,
            "/help": self._reply_help,
        }
        handler = _DISPATCH.get(text)
        if handler:
            handler()

    def _reply_status(self) -> None:
        status = self._get_status()
        lines = ["📊 Bot Status"]
        for symbol, info in sorted(status.items()):
            phase = info.get("phase", "UNKNOWN")
            icon = _PHASE_ICONS.get(phase, "❓")
            direction = f" {info['direction']}" if info.get("direction") else ""
            ticket = f" #{info['ticket']}" if info.get("ticket") else ""
            lines.append(f"{icon} {symbol}: {phase}{direction}{ticket}")
        self._send("\n".join(lines))

    def _reply_positions(self) -> None:
        positions = self._get_positions()
        if not positions:
            self._send("📭 No open positions")
            return
        lines = [f"📂 Open positions ({len(positions)})"]
        for p in positions:
            sign = "+" if p.get("profit", 0) >= 0 else ""
            lines.append(
                f"{'🟢' if p['type'] == 'BUY' else '🔴'} {p['symbol']} "
                f"{p['type']} {p['volume']}lot | "
                f"P&L: {sign}{p.get('profit', 0):.2f} | "
                f"#{p['ticket']}"
            )
        self._send("\n".join(lines))

    def _reply_balance(self) -> None:
        info = self._get_balance()
        if info is None:
            self._send("⚠️ Account info unavailable — MT5 not connected")
            return
        self._send(
            f"💰 Account #{info['login']}\n"
            f"Balance: {info['balance']:.2f}\n"
            f"Equity:  {info['equity']:.2f}"
        )

    def _reply_help(self) -> None:
        self._send(_HELP_TEXT)

    def _send(self, text: str) -> None:
        try:
            requests.post(
                f"{self._base}/sendMessage",
                json={"chat_id": self._chat_id, "text": text},
                timeout=5.0,
            )
        except Exception as exc:
            logger.warning("TelegramListener send error: %s", exc)
