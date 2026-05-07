"""Technical-indicator helpers (no TA-Lib dependency).

All functions return ``pandas.Series`` (or a tuple of series) aligned to the
input index. NaNs from rolling-window warm-up are *not* filled here; callers
that need them filled must do so explicitly. ``add_indicators`` is the only
exception: it backfills warm-up NaNs because the RL/Hybrid path requires
finite features in its observation window.
"""

from __future__ import annotations

import pandas as pd
import numpy as np


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Wilder-style RSI; neutral 50 fallback while the window is warming up."""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calculate_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Simple-moving-average ATR over true range."""
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def calculate_macd(
    prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Standard MACD: returns (macd_line, signal_line, histogram).

    ``adjust=False`` matches TA-Lib / TradingView defaults so values are
    comparable to common charting tools.
    """
    fast_ema = prices.ewm(span=fast, adjust=False).mean()
    slow_ema = prices.ewm(span=slow, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_bollinger_bands(
    prices: pd.Series, period: int = 20, num_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (middle, upper, lower) Bollinger Bands."""
    middle = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std(ddof=0)
    upper = middle + num_std * std
    lower = middle - num_std * std
    return middle, upper, lower


def calculate_stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[pd.Series, pd.Series]:
    """Stochastic oscillator. Returns (%K, %D) on the standard 0-100 scale."""
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    range_ = (highest_high - lowest_low).replace(0, np.nan)
    k = 100 * (close - lowest_low) / range_
    d = k.rolling(window=d_period).mean()
    return k.fillna(50), d.fillna(50)


def calculate_ema(prices: pd.Series, span: int) -> pd.Series:
    """Exponential moving average with TradingView-compatible smoothing."""
    return prices.ewm(span=span, adjust=False).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add the indicator set used by the RL observation window and dashboards.

    Returns a *copy* with new columns. Warm-up NaNs are back-filled because
    the RL agent's observation window requires finite features.
    """
    work_df = df.copy()

    work_df["ema_fast"] = calculate_ema(work_df["close"], span=12)
    work_df["ema_slow"] = calculate_ema(work_df["close"], span=26)
    work_df["ema_200"] = calculate_ema(work_df["close"], span=200)

    work_df["rsi"] = calculate_rsi(work_df["close"], period=14)

    work_df["atr_value"] = calculate_atr(
        work_df["high"], work_df["low"], work_df["close"], period=14
    )

    macd_line, macd_signal, macd_hist = calculate_macd(work_df["close"])
    work_df["macd"] = macd_line
    work_df["macd_signal"] = macd_signal
    work_df["macd_hist"] = macd_hist

    bb_mid, bb_up, bb_low = calculate_bollinger_bands(work_df["close"])
    work_df["bb_mid"] = bb_mid
    work_df["bb_upper"] = bb_up
    work_df["bb_lower"] = bb_low
    bb_range = (bb_up - bb_low).replace(0, np.nan)
    work_df["bb_pct_b"] = ((work_df["close"] - bb_low) / bb_range).fillna(0.5)

    stoch_k, stoch_d = calculate_stochastic(
        work_df["high"], work_df["low"], work_df["close"]
    )
    work_df["stoch_k"] = stoch_k
    work_df["stoch_d"] = stoch_d

    return work_df.bfill()


def higher_timeframe_trend(
    higher_tf_candles: pd.DataFrame, ema_span: int = 200
) -> int:
    """Classify the higher-timeframe trend as +1 / 0 / -1.

    +1 when the latest close > EMA(span); -1 when below; 0 when there is
    insufficient history to compute the EMA.
    """
    if higher_tf_candles is None or len(higher_tf_candles) == 0:
        return 0
    if len(higher_tf_candles) < ema_span:
        return 0
    ema = calculate_ema(higher_tf_candles["close"], span=ema_span).iloc[-1]
    last_close = higher_tf_candles["close"].iloc[-1]
    if last_close > ema:
        return 1
    if last_close < ema:
        return -1
    return 0
