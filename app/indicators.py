"""
Standard technical-indicator formulas, hand-rolled in pandas.

Deliberately NOT using a library like `ta` or `pandas-ta`: these formulas are
~5 lines of pandas each, and pulling in a dependency (some of which wrap
TA-Lib's C extension, a notoriously painful install on Windows/CI runners)
for something this small isn't worth the install-time risk.
"""
from __future__ import annotations

import pandas as pd


def moving_average(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=1).mean()


def bollinger_bands(series: pd.Series, window: int = 20, num_std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = series.rolling(window=window, min_periods=1).mean()
    std = series.rolling(window=window, min_periods=1).std(ddof=0)
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()

    rs = avg_gain / avg_loss
    result = 100 - (100 / (1 + rs))
    # avg_loss == 0: no losses in the window -> maximally overbought (100),
    # unless there was also no gain (flat series) -> neutral (50).
    result = result.where(avg_loss != 0, other=pd.NA)
    no_loss_mask = avg_loss == 0
    result[no_loss_mask & (avg_gain > 0)] = 100.0
    result[no_loss_mask & (avg_gain == 0)] = 50.0
    return result.astype(float)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram
