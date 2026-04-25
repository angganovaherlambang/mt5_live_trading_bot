# gui/updates.py
"""
GUI update handlers and event callbacks — mixed into the main app class via UpdatesMixin.
"""
import tkinter as tk
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class UpdatesMixin:
    """Display update and event handler methods. Mixed into the main app class."""

    def process_phase_updates(self):
        """Drain the update_queue and refresh the display. Called by tkinter .after()."""
        try:
            while True:
                update = self.update_queue.get_nowait()
                self._apply_phase_update(update)
        except Exception:
            pass
        self.root.after(1000, self.process_phase_updates)

    def _apply_phase_update(self, update: dict):
        """Update the phases treeview for a single symbol."""
        symbol = update["symbol"]
        values = (
            symbol,
            update.get("phase", ""),
            update.get("direction", ""),
            update.get("pullback_count", 0),
            "YES" if update.get("window_open") else "NO",
        )
        # Update existing row or insert new
        for item in self.phases_tree.get_children():
            if self.phases_tree.item(item)["values"][0] == symbol:
                self.phases_tree.item(item, values=values)
                return
        self.phases_tree.insert("", tk.END, values=values)

    def terminal_log(self, message: str, level: str = "INFO"):
        """Append a color-tagged line to the terminal widget."""
        self.terminal_text.configure(state=tk.NORMAL)
        timestamp = datetime.now(tz=timezone.utc).strftime("%H:%M:%S")
        self.terminal_text.insert(tk.END, f"[{timestamp}] {message}\n", level)
        self.terminal_text.see(tk.END)
        self.terminal_text.configure(state=tk.DISABLED)

    def update_time(self):
        """Update the status bar clock every second."""
        now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self.time_label.configure(text=now)
        self.root.after(1000, self.update_time)

    def on_closing(self):
        """Clean shutdown: stop the monitor loop, save state, destroy window."""
        if hasattr(self, "monitor_loop") and self.monitor_loop:
            self.monitor_loop.stop()
        self.root.destroy()
