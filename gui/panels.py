# gui/panels.py
"""
Left/right panel layout setup.
These methods are mixed into AdvancedMT5TradingMonitorGUI via PanelsMixin.
"""
import tkinter as tk
from tkinter import ttk


class PanelsMixin:
    """GUI panel layout methods. Mixed into the main app class."""

    def setup_left_panel(self):
        """Create the left notebook (Strategy Phases, Configuration, Indicators tabs)."""
        self.left_frame = ttk.Frame(self.main_paned)
        self.main_paned.add(self.left_frame, weight=1)
        self.left_notebook = ttk.Notebook(self.left_frame)
        self.left_notebook.pack(fill=tk.BOTH, expand=True)

    def setup_right_panel(self):
        """Create the right notebook (Charts, Terminal, Window Markers tabs)."""
        self.right_frame = ttk.Frame(self.main_paned)
        self.main_paned.add(self.right_frame, weight=2)
        self.right_notebook = ttk.Notebook(self.right_frame)
        self.right_notebook.pack(fill=tk.BOTH, expand=True)

    def create_status_bar(self):
        """Bottom bar: connection status + clock."""
        self.status_bar = ttk.Frame(self.root, relief=tk.SUNKEN)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_label = ttk.Label(self.status_bar, text="Disconnected")
        self.status_label.pack(side=tk.LEFT, padx=5)
        self.time_label = ttk.Label(self.status_bar, text="")
        self.time_label.pack(side=tk.RIGHT, padx=5)
