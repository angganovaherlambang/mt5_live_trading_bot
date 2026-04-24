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
