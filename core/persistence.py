"""
Atomic JSON persistence for strategy PhaseState objects.

Uses write-to-temp + rename for crash safety.
"""
from __future__ import annotations
import json
import logging
import time
from pathlib import Path

from core.state import PhaseState, Phase

logger = logging.getLogger(__name__)


def save_states(states: dict[str, PhaseState], path: Path) -> None:
    """Atomically write states to JSON. Safe against partial writes."""
    data = {
        "saved_at": time.time(),
        "states": {
            symbol: {
                "phase": state.phase.value,
                "pullback_count": state.pullback_count,
                "window_open": state.window_open,
                "window_expiry_bar": state.window_expiry_bar,
                "window_breakout_level": state.window_breakout_level,
                "signal_candle_index": state.signal_candle_index,
                "signal_bar_time": state.signal_bar_time,
                "direction": state.direction,
                "active_ticket": state.active_ticket,
            }
            for symbol, state in states.items()
        },
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)
    logger.debug("Saved %d symbol states to %s", len(states), path)


def load_states(path: Path, max_age_seconds: int = 1800) -> dict[str, PhaseState]:
    """
    Load states from JSON. Returns {} if file missing, corrupt, or stale.
    max_age_seconds: reject states older than this (default 30 minutes).
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cannot load state from %s: %s", path, exc)
        return {}

    age = time.time() - data.get("saved_at", 0)
    if age > max_age_seconds:
        logger.info("State file is %.0f seconds old (max %d), ignoring", age, max_age_seconds)
        return {}

    result: dict[str, PhaseState] = {}
    for symbol, raw in data.get("states", {}).items():
        try:
            state = PhaseState(
                symbol=symbol,
                phase=Phase(raw["phase"]),
                pullback_count=raw.get("pullback_count", 0),
                window_open=raw.get("window_open", False),
                window_expiry_bar=raw.get("window_expiry_bar", 0),
                window_breakout_level=raw.get("window_breakout_level"),
                signal_candle_index=raw.get("signal_candle_index", 0),
                signal_bar_time=raw.get("signal_bar_time"),
                direction=raw.get("direction"),
                active_ticket=raw.get("active_ticket"),
            )
            result[symbol] = state
        except (KeyError, ValueError) as exc:
            logger.warning("Skipping malformed state for %s: %s", symbol, exc)
    return result
