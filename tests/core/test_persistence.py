import json
import pytest
from pathlib import Path
from core.state import PhaseState, Phase
from core.persistence import save_states, load_states


def test_round_trip(tmp_path):
    states = {
        "EURUSD": PhaseState(symbol="EURUSD", phase=Phase.ARMED_LONG, pullback_count=1),
        "XAUUSD": PhaseState(symbol="XAUUSD"),
    }
    path = tmp_path / "state.json"
    save_states(states, path)
    loaded = load_states(path, max_age_seconds=3600)
    assert loaded["EURUSD"].phase == Phase.ARMED_LONG
    assert loaded["EURUSD"].pullback_count == 1
    assert loaded["XAUUSD"].phase == Phase.SCANNING


def test_stale_state_returns_empty(tmp_path):
    import time
    states = {"EURUSD": PhaseState(symbol="EURUSD", phase=Phase.ARMED_LONG)}
    path = tmp_path / "state.json"
    save_states(states, path)
    # max_age=0 forces staleness
    loaded = load_states(path, max_age_seconds=0)
    assert loaded == {}


def test_missing_file_returns_empty(tmp_path):
    loaded = load_states(tmp_path / "nonexistent.json", max_age_seconds=3600)
    assert loaded == {}


def test_active_ticket_round_trip(tmp_path):
    """active_ticket survives save/load cycle."""
    states = {
        "EURUSD": PhaseState(symbol="EURUSD", phase=Phase.IN_TRADE),
    }
    states["EURUSD"].active_ticket = 99999
    path = tmp_path / "state.json"
    save_states(states, path)
    loaded = load_states(path, max_age_seconds=3600)
    assert loaded["EURUSD"].phase == Phase.IN_TRADE
    assert loaded["EURUSD"].active_ticket == 99999


def test_active_ticket_none_round_trip(tmp_path):
    """active_ticket=None survives save/load cycle."""
    states = {"EURUSD": PhaseState(symbol="EURUSD")}
    path = tmp_path / "state.json"
    save_states(states, path)
    loaded = load_states(path, max_age_seconds=3600)
    assert loaded["EURUSD"].active_ticket is None
