from core.state import PhaseState, Phase


def test_initial_state_is_scanning():
    s = PhaseState(symbol="EURUSD")
    assert s.phase == Phase.SCANNING
    assert s.pullback_count == 0
    assert s.window_open is False


def test_reset_clears_to_scanning():
    s = PhaseState(symbol="EURUSD", phase=Phase.ARMED_LONG, pullback_count=2)
    s.reset()
    assert s.phase == Phase.SCANNING
    assert s.pullback_count == 0


def test_in_trade_is_valid_phase():
    s = PhaseState(symbol="EURUSD", phase=Phase.IN_TRADE)
    assert s.phase == Phase.IN_TRADE


def test_active_ticket_defaults_to_none():
    s = PhaseState(symbol="EURUSD")
    assert s.active_ticket is None


def test_reset_clears_active_ticket():
    s = PhaseState(symbol="EURUSD", phase=Phase.IN_TRADE)
    s.active_ticket = 12345
    s.reset()
    assert s.phase == Phase.SCANNING
    assert s.active_ticket is None
