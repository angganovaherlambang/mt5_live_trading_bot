# main.py
"""
Entry point for the MT5 Advanced Monitor.

Run: python main.py
"""
import tkinter as tk
from gui.app import AdvancedMT5TradingMonitorGUI


def main():
    root = tk.Tk()
    root.geometry("1400x900")
    app = AdvancedMT5TradingMonitorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
