import numpy as np
import pandas as pd
import pytest

from edgebet.betting.odds import best_price, devig, devig_frame, overround


@pytest.mark.parametrize("method", ["multiplicative", "power", "shin"])
def test_devig_sums_to_one_and_keeps_order(method):
    odds = np.array([1.80, 3.60, 4.80])
    p = devig(odds, method)
    assert abs(p.sum() - 1.0) < 1e-9
    assert p[0] > p[1] > p[2]
    assert overround(odds) > 0.04


def test_power_and_shin_reduce_longshot_more_than_multiplicative():
    odds = np.array([1.25, 6.0, 12.0])
    mult = devig(odds, "multiplicative")
    power = devig(odds, "power")
    shin = devig(odds, "shin")
    assert power[2] < mult[2]
    assert shin[2] < mult[2]


def test_devig_frame_handles_nan():
    df = pd.DataFrame({"h": [2.0, np.nan], "d": [3.4, 3.0], "a": [3.6, 2.5]})
    out = devig_frame(df, ["h", "d", "a"], "power")
    assert abs(out[0].sum() - 1.0) < 1e-9
    assert np.isnan(out[1]).all()


def test_best_price():
    book, price = best_price({"a": 2.0, "b": float("nan"), "c": 2.15})
    assert book == "c" and price == 2.15
