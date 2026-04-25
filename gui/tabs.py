# gui/tabs.py
"""
Notebook tab creation methods — mixed into the main app class via TabsMixin.
Each method populates one tab of the left or right notebook.
"""
import tkinter as tk
from tkinter import ttk


class TabsMixin:
    """Tab creation methods. Mixed into the main app class."""

    def create_strategy_phases_tab(self):
        """Treeview showing per-symbol phase, direction, pullback count."""
        frame = ttk.Frame(self.left_notebook)
        self.left_notebook.add(frame, text="Strategy Phases")
        cols = ("Symbol", "Phase", "Direction", "Pullbacks", "Window")
        self.phases_tree = ttk.Treeview(frame, columns=cols, show="headings")
        for col in cols:
            self.phases_tree.heading(col, text=col)
            self.phases_tree.column(col, width=90)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.phases_tree.yview)
        self.phases_tree.configure(yscrollcommand=scrollbar.set)
        self.phases_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def create_terminal_tab(self):
        """Scrollable monospace text widget for color-coded log output."""
        frame = ttk.Frame(self.right_notebook)
        self.right_notebook.add(frame, text="Terminal Output")
        self.terminal_text = tk.Text(
            frame, state=tk.DISABLED, font=("Courier", 9),
            bg="#1e1e1e", fg="#d4d4d4", wrap=tk.WORD,
        )
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.terminal_text.yview)
        self.terminal_text.configure(yscrollcommand=scrollbar.set)
        self.terminal_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # Color tags
        self.terminal_text.tag_configure("INFO", foreground="#d4d4d4")
        self.terminal_text.tag_configure("WARNING", foreground="#ffcc00")
        self.terminal_text.tag_configure("ERROR", foreground="#f44747")
        self.terminal_text.tag_configure("ARMED", foreground="#4ec9b0")
        self.terminal_text.tag_configure("WINDOW", foreground="#569cd6")

    def create_configuration_tab(self):
        """Text widget displaying selected symbol's config parameters."""
        frame = ttk.Frame(self.left_notebook)
        self.left_notebook.add(frame, text="Configuration")
        self.config_text = tk.Text(frame, state=tk.DISABLED, font=("Courier", 9))
        self.config_text.pack(fill=tk.BOTH, expand=True)

    def create_indicators_tab(self):
        """Text widget displaying current indicator values."""
        frame = ttk.Frame(self.left_notebook)
        self.left_notebook.add(frame, text="Indicators")
        self.indicators_text = tk.Text(frame, state=tk.DISABLED, font=("Courier", 9))
        self.indicators_text.pack(fill=tk.BOTH, expand=True)

    def create_window_markers_tab(self):
        """Treeview showing all active breakout windows."""
        frame = ttk.Frame(self.right_notebook)
        self.right_notebook.add(frame, text="Window Markers")
        cols = ("Symbol", "Direction", "Breakout Level", "Expires")
        self.windows_tree = ttk.Treeview(frame, columns=cols, show="headings")
        for col in cols:
            self.windows_tree.heading(col, text=col)
        self.windows_tree.pack(fill=tk.BOTH, expand=True)
