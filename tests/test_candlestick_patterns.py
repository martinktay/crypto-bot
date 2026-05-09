"""Tests for classic candlestick pattern detection."""

import pandas as pd

from app.utils import candlestick_patterns as cp


def _df(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    o, h, l, c = zip(*rows)
    n = len(rows)
    return pd.DataFrame(
        {
            "ts": range(n),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": [1.0] * n,
        }
    )


def test_bullish_engulfing_detected() -> None:
    # prev bearish, last bullish engulfs
    df = _df(
        [
            (100, 101, 99, 98),
            (97, 102, 96, 101),
        ]
    )
    bear, bull = cp.describe_active_patterns(df)
    assert "bullish engulfing" in bull


def test_bearish_engulfing_vetoes_long() -> None:
    df = _df(
        [
            (10, 12, 9, 12),
            (13, 14, 8, 9),
        ]
    )
    v, why = cp.veto_long(df)
    assert v is True
    assert "bearish engulfing" in why


def test_neutral_trend_no_shooting_star_noise() -> None:
    # flat-ish closes — no 4-bar uptrend for shooting star
    flat = [(100 + i * 0.01, 101.0, 99.0, 100.0 + i * 0.01) for i in range(6)]
    df = _df(flat)
    bear, bull = cp.describe_active_patterns(df)
    assert "shooting star" not in bear
