# gui/app.py
"""
Main application class — a slim orchestrator that wires modules together.

Layout and update logic live in PanelsMixin, TabsMixin, UpdatesMixin.
Trading logic lives in core/ and monitor/.
"""
from __future__ import annotations
import queue
import tkinter as tk
from tkinter import ttk
from pathlib import Path

from core.config_loader import load_all_configs
from core.persistence import load_states
from mt5.connection import MT5Connection
from monitor.loop import MonitorLoop
from gui.panels import PanelsMixin
from gui.tabs import TabsMixin
from gui.updates import UpdatesMixin

SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD", "AUDUSD", "XAGUSD", "USDCHF", "EURJPY", "USDJPY"]
STRATEGIES_DIR = Path("strategies")


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
        self.monitor_loop: MonitorLoop | None = None

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
            self.monitor_loop = MonitorLoop(
                connection=self.connection,
                configs=self.configs,
                symbols=SYMBOLS,
                update_queue=self.update_queue,
            )
            self.monitor_loop.start()
        else:
            self.status_label.configure(text="Disconnected — check MT5")
            self.terminal_log("MT5 connection failed", "ERROR")
