# gui/app.py
"""
Main application class — a slim orchestrator that wires modules together.

Layout and update logic live in PanelsMixin, TabsMixin, UpdatesMixin.
Trading logic lives in core/ and monitor/.
"""
from __future__ import annotations
import os
import queue
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Optional

from core.config_loader import load_all_configs
from core.persistence import load_states
from mt5.connection import MT5Connection
from monitor.loop import MonitorLoop
from monitor.trader import OrderExecutor
from notify.telegram import TelegramNotifier
from gui.panels import PanelsMixin
from gui.tabs import TabsMixin
from gui.updates import UpdatesMixin

SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD", "AUDUSD", "XAGUSD", "USDCHF", "EURJPY", "USDJPY"]
STRATEGIES_DIR = Path("strategies")
RISK_PCT = 0.01
MAX_LOT = 0.5


def _build_notifier() -> Optional[TelegramNotifier]:
    """Read TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from env. Returns None if not set."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        return TelegramNotifier(token=token, chat_id=chat_id)
    return None


class AdvancedMT5TradingMonitorGUI(PanelsMixin, TabsMixin, UpdatesMixin):
    """
    Top-level application class.

    Responsibilities:
    - Build the tkinter window
    - Initialise MT5 connection
    - Load strategy configs
    - Start MonitorLoop
    - Wire GUI callbacks
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MT5 Advanced Monitor")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.update_queue: queue.Queue = queue.Queue()
        self.connection = MT5Connection()
        self.configs = load_all_configs(STRATEGIES_DIR, SYMBOLS)
        self.notifier: Optional[TelegramNotifier] = _build_notifier()
        self.monitor_loop: MonitorLoop | None = None
        self.order_executor: OrderExecutor | None = None

        self._build_gui()
        self._connect_and_start()
        self.process_phase_updates()
        self.update_time()

    def _build_gui(self) -> None:
        self.main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True)
        self.setup_left_panel()
        self.setup_right_panel()
        self.create_strategy_phases_tab()
        self.create_configuration_tab()
        self.create_indicators_tab()
        self.create_terminal_tab()
        self.create_window_markers_tab()
        self.create_status_bar()

    def _connect_and_start(self) -> None:
        if self.connection.connect():
            self.status_label.configure(text="Connected")
            self.terminal_log("MT5 connected", "INFO")
            self.order_executor = OrderExecutor(
                connection=self.connection,
                configs=self.configs,
                risk_pct=RISK_PCT,
                max_lot=MAX_LOT,
                demo_mode=True,
                notifier=self.notifier,
            )
            self.monitor_loop = MonitorLoop(
                connection=self.connection,
                configs=self.configs,
                symbols=SYMBOLS,
                update_queue=self.update_queue,
                order_executor=self.order_executor,
                notifier=self.notifier,
            )
            self.monitor_loop.start()
            self._refresh_mode_label()
            tg = " + Telegram" if self.notifier else ""
            self.terminal_log(f"OrderExecutor started — DEMO mode{tg}", "INFO")
        else:
            self.status_label.configure(text="Disconnected — check MT5")
            self.terminal_log("MT5 connection failed", "ERROR")

    def toggle_demo_mode(self) -> None:
        """Switch between DEMO and LIVE order execution. Requires confirmation for LIVE."""
        if self.order_executor is None:
            return
        if self.order_executor.demo_mode:
            from tkinter import messagebox
            if messagebox.askyesno(
                "Enable LIVE Trading",
                "Switch to LIVE mode?\n\nReal orders will be placed on your MT5 account.",
            ):
                self.order_executor.demo_mode = False
                self.terminal_log("Switched to LIVE mode — orders will be executed", "WARNING")
        else:
            self.order_executor.demo_mode = True
            self.terminal_log("Switched to DEMO mode — orders will only be logged", "INFO")
        self._refresh_mode_label()

    def _refresh_mode_label(self) -> None:
        if self.order_executor is None:
            return
        if self.order_executor.demo_mode:
            self.mode_label.configure(text="DEMO", foreground="#ffcc00")
        else:
            self.mode_label.configure(text="LIVE", foreground="#f44747")
