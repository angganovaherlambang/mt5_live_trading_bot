import pytest
from mt5.risk import calculate_sl_tp, calculate_lot_size


class TestCalculateSlTp:
    def test_long_sl_below_entry_tp_above(self):
        sl, tp = calculate_sl_tp(
            direction="LONG",
            entry_price=1.1000,
            atr=0.000300,
            sl_multiplier=1.5,
            tp_multiplier=10.0,
        )
        assert sl < 1.1000, "SL must be below entry for LONG"
        assert tp > 1.1000, "TP must be above entry for LONG"

    def test_long_sl_distance_equals_atr_times_multiplier(self):
        sl, tp = calculate_sl_tp("LONG", 1.1000, 0.000300, 1.5, 10.0)
        assert abs((1.1000 - sl) - 0.000300 * 1.5) < 1e-8

    def test_long_tp_distance_equals_atr_times_multiplier(self):
        sl, tp = calculate_sl_tp("LONG", 1.1000, 0.000300, 1.5, 10.0)
        assert abs((tp - 1.1000) - 0.000300 * 10.0) < 1e-8

    def test_short_sl_above_entry_tp_below(self):
        sl, tp = calculate_sl_tp("SHORT", 1.1000, 0.000300, 1.5, 10.0)
        assert sl > 1.1000, "SL must be above entry for SHORT"
        assert tp < 1.1000, "TP must be below entry for SHORT"

    def test_short_distances_correct(self):
        sl, tp = calculate_sl_tp("SHORT", 1.1000, 0.000300, 1.5, 10.0)
        assert abs((sl - 1.1000) - 0.000300 * 1.5) < 1e-8
        assert abs((1.1000 - tp) - 0.000300 * 10.0) < 1e-8

    def test_uses_config_multipliers(self, eurusd_config):
        sl, tp = calculate_sl_tp(
            direction="LONG",
            entry_price=1.1000,
            atr=0.000200,
            sl_multiplier=eurusd_config["long_atr_sl_multiplier"],
            tp_multiplier=eurusd_config["long_atr_tp_multiplier"],
        )
        expected_sl = 1.1000 - 0.000200 * eurusd_config["long_atr_sl_multiplier"]
        expected_tp = 1.1000 + 0.000200 * eurusd_config["long_atr_tp_multiplier"]
        assert abs(sl - expected_sl) < 1e-8
        assert abs(tp - expected_tp) < 1e-8


class TestCalculateLotSize:
    def test_basic_lot_calculation(self):
        lot = calculate_lot_size(
            risk_amount=100.0,
            sl_pips=30.0,
            pip_value_per_lot=10.0,
            min_lot=0.01,
            max_lot=1.0,
            lot_step=0.01,
        )
        assert 0.01 <= lot <= 1.0

    def test_respects_max_lot(self):
        lot = calculate_lot_size(
            risk_amount=100000.0,
            sl_pips=1.0,
            pip_value_per_lot=10.0,
            min_lot=0.01,
            max_lot=0.5,
            lot_step=0.01,
        )
        assert lot <= 0.5

    def test_respects_min_lot(self):
        lot = calculate_lot_size(
            risk_amount=0.001,
            sl_pips=100.0,
            pip_value_per_lot=10.0,
            min_lot=0.01,
            max_lot=1.0,
            lot_step=0.01,
        )
        assert lot >= 0.01

    def test_lot_is_rounded_to_step(self):
        lot = calculate_lot_size(
            risk_amount=100.0,
            sl_pips=30.0,
            pip_value_per_lot=10.0,
            min_lot=0.01,
            max_lot=1.0,
            lot_step=0.01,
        )
        assert round(lot % 0.01, 6) == 0.0

    def test_jpy_pip_value_differs(self):
        lot = calculate_lot_size(
            risk_amount=100.0,
            sl_pips=30.0,
            pip_value_per_lot=9.15,
            min_lot=0.01,
            max_lot=1.0,
            lot_step=0.01,
        )
        assert lot >= 0.01
