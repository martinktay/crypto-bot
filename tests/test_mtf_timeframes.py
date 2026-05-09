"""Multi-timeframe alignment helpers."""

import pandas as pd

from app.utils.indicators import resolve_htf_gate
from app.utils.timeframes import (
    is_alltime_token,
    normalize_alignment_timeframe,
    timeframe_to_minutes,
)


def test_timeframe_to_minutes_ordering() -> None:
    assert timeframe_to_minutes("15m") < timeframe_to_minutes("1h")
    assert timeframe_to_minutes("1h") < timeframe_to_minutes("4h")
    assert timeframe_to_minutes("4h") < timeframe_to_minutes("1d")
    assert timeframe_to_minutes("1d") < timeframe_to_minutes("1w")
    assert timeframe_to_minutes("1w") < timeframe_to_minutes("1M")


def test_alltime_normalizes_to_monthly() -> None:
    assert normalize_alignment_timeframe("all") == "1M"
    assert is_alltime_token("alltime")


def test_resolve_htf_gate_multi_blocks() -> None:
    n = 250
    up = pd.DataFrame(
        {
            "ts": range(n),
            "open": [200.0] * n,
            "high": [201.0] * n,
            "low": [199.0] * n,
            "close": [200.0 + i * 0.1 for i in range(n)],
            "volume": [1.0] * n,
        }
    )
    down = up.copy()
    down["close"] = [300.0 - i * 0.1 for i in range(n)]

    bl, bs, label = resolve_htf_gate(
        {"multi_htf_candles": {"1h": up, "4h": down}},
    )
    assert bl is True
    assert bs is True
    assert "MTF" in label


def test_resolve_htf_gate_single_same_as_before() -> None:
    n = 250
    flat = pd.DataFrame(
        {
            "ts": range(n),
            "open": [200.0] * n,
            "high": [201.0] * n,
            "low": [199.0] * n,
            "close": [200.0] * n,
            "volume": [1.0] * n,
        }
    )
    bl, bs, _ = resolve_htf_gate({"higher_tf_candles": flat})
    assert bl is False
    assert bs is False
