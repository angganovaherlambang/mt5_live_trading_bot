"""
Strategy configuration loading and validation.

Parses Python-syntax strategy files (strategies/sunrise_ogle_*.py) into plain dicts.
No MT5 or GUI dependency.
"""
from __future__ import annotations
import re
import importlib.util
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Parameters always required when ENABLE_LONG_TRADES=True
_REQUIRED_LONG_PARAMS = [
    "ema_fast_length", "ema_medium_length", "ema_slow_length",
    "ema_confirm_length", "ema_filter_price_length", "atr_length",
    "long_atr_sl_multiplier", "long_atr_tp_multiplier",
    "LONG_PULLBACK_MAX_CANDLES", "LONG_ENTRY_WINDOW_PERIODS",
    "USE_WINDOW_TIME_OFFSET", "WINDOW_OFFSET_MULTIPLIER",
    "WINDOW_PRICE_OFFSET_MULTIPLIER",
]

# Parameters required only when ENABLE_SHORT_TRADES=True
_REQUIRED_SHORT_PARAMS = [
    "short_atr_sl_multiplier", "short_atr_tp_multiplier",
    "SHORT_PULLBACK_MAX_CANDLES", "SHORT_ENTRY_WINDOW_PERIODS",
]


def extract_numeric_value(line: str) -> Optional[float]:
    """Parse 'key = <number>' from a single config file line. Returns None if not numeric."""
    match = re.search(r"=\s*(-?\d+\.?\d*(?:e[+-]?\d+)?)\s*$", line, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def extract_bool_value(line: str) -> Optional[bool]:
    """Parse 'key = True/False' from a single config file line. Returns None if not boolean."""
    match = re.search(r"=\s*(True|False)\s*$", line)
    if match:
        return match.group(1) == "True"
    return None


def parse_strategy_config(strategy_path: Path) -> dict:
    """
    Load a strategy file and return its top-level scalar assignments as a dict.

    Supports integer, float, bool, and string values.
    The SunriseOgle class instance params (ema_fast_length etc.) are also captured
    by scanning for bare assignments inside the class body.
    """
    config: dict = {}
    try:
        source = strategy_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Cannot read strategy file %s: %s", strategy_path, exc)
        return config

    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key_part, _, _ = stripped.partition("=")
        key = key_part.strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            continue

        bool_val = extract_bool_value(stripped)
        if bool_val is not None:
            config[key] = bool_val
            continue

        num_val = extract_numeric_value(stripped)
        if num_val is not None:
            config[key] = num_val
            continue

        # String values
        str_match = re.search(r"=\s*['\"](.+)['\"]\s*$", stripped)
        if str_match:
            config[key] = str_match.group(1)

    return config


def validate_critical_params(config: dict) -> list[str]:
    """
    Return a list of missing parameter names.
    An empty list means the config is valid.
    """
    missing = []
    if config.get("ENABLE_LONG_TRADES", False):
        for p in _REQUIRED_LONG_PARAMS:
            if p not in config:
                missing.append(p)
    if config.get("ENABLE_SHORT_TRADES", False):
        for p in _REQUIRED_SHORT_PARAMS:
            if p not in config:
                missing.append(p)
    return missing


def load_all_configs(strategies_dir: Path, symbols: list[str]) -> dict[str, dict]:
    """
    Load configs for all symbols. Returns {symbol: config_dict}.
    Symbols with invalid configs get an empty dict.
    """
    result: dict[str, dict] = {}
    for symbol in symbols:
        filename = f"sunrise_ogle_{symbol.lower()}.py"
        path = strategies_dir / filename
        if not path.exists():
            logger.warning("Strategy file not found: %s", path)
            result[symbol] = {}
            continue
        cfg = parse_strategy_config(path)
        missing = validate_critical_params(cfg)
        if missing:
            logger.error("Symbol %s missing params: %s", symbol, missing)
            result[symbol] = {}
        else:
            result[symbol] = cfg
    return result
