"""
Unit tests for app/indicators.py — hand-rolled MA/Bollinger/RSI/MACD.

RSI in particular had a real bug caught here during development: a naive
`avg_gain / avg_loss` with avg_loss replaced to NaN on zero collapsed a
monotonic uptrend to a neutral 50 instead of an overbought ~100.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import indicators as ind  # noqa: E402

UP = pd.Series([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20.0])
DOWN = pd.Series([20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10.0])
FLAT = pd.Series([10.0] * 11)


def test_moving_average_matches_manual_computation():
    ma3 = ind.moving_average(UP, 3)
    assert ma3.iloc[-1] == pytest.approx((18 + 19 + 20) / 3)


def test_bollinger_bands_upper_mid_lower_ordering():
    upper, mid, lower = ind.bollinger_bands(UP, window=5)
    assert (upper >= mid).all()
    assert (mid >= lower).all()


def test_bollinger_bands_collapse_to_mid_on_flat_series():
    upper, mid, lower = ind.bollinger_bands(FLAT, window=5)
    assert (upper == mid).all()
    assert (lower == mid).all()


def test_rsi_approaches_100_on_monotonic_uptrend():
    result = ind.rsi(UP, window=5)
    assert result.iloc[-1] == pytest.approx(100.0)


def test_rsi_approaches_0_on_monotonic_downtrend():
    result = ind.rsi(DOWN, window=5)
    assert result.iloc[-1] == pytest.approx(0.0)


def test_rsi_is_neutral_on_flat_series():
    result = ind.rsi(FLAT, window=5)
    assert result.iloc[-1] == pytest.approx(50.0)


def test_rsi_stays_within_bounds_on_mixed_series():
    mixed = pd.Series([10, 11, 10, 11, 10, 12, 9, 13, 8, 14, 20.0])
    result = ind.rsi(mixed, window=5)
    # The first `window` values are NaN (not enough data yet) by design,
    # same as any rolling/ewm indicator — only the warmed-up tail is checked.
    assert result.dropna().between(0, 100).all()


def test_macd_histogram_equals_macd_minus_signal():
    macd_line, signal_line, hist = ind.macd(UP, fast=3, slow=6, signal=2)
    pd.testing.assert_series_equal(hist, macd_line - signal_line, check_names=False)
