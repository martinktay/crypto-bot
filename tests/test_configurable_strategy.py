"""Tests for configurable EMA/RSI strategy parameters."""

import pandas as pd

from app.schemas.signal import SignalContract
from app.strategies.ema_rsi import EmaRsiStrategy


def _candles(n: int = 60, trend: str = "up") -> pd.DataFrame:
    """Generate synthetic candle data with a given trend."""
    if trend == "up":
        close = [100 + i * 0.5 for i in range(n)]
    elif trend == "down":
        close = [130 - i * 0.5 for i in range(n)]
    else:
        close = [100 + (i % 5) * 0.1 for i in range(n)]
    return pd.DataFrame(
        {
            "ts": list(range(n)),
            "open": close,
            "high": [c + 1 for c in close],
            "low": [c - 1 for c in close],
            "close": close,
            "volume": [10_000] * n,
        }
    )


def test_ema_rsi_returns_valid_contract() -> None:
    signal = EmaRsiStrategy().generate("BTC/USDT", "15m", _candles())
    assert isinstance(signal, SignalContract)
    assert signal.symbol == "BTC/USDT"
    assert signal.timeframe == "15m"
    assert 0 <= signal.confidence <= 100
    assert signal.reason  # non-empty reason


def test_uptrend_produces_long_or_hold() -> None:
    signal = EmaRsiStrategy().generate("BTC/USDT", "15m", _candles(trend="up"))
    assert signal.signal.value in ("LONG", "HOLD")


def test_downtrend_produces_short_or_hold() -> None:
    signal = EmaRsiStrategy().generate("BTC/USDT", "15m", _candles(trend="down"))
    assert signal.signal.value in ("SHORT", "HOLD")


def test_stop_loss_is_below_entry_for_long() -> None:
    signal = EmaRsiStrategy().generate("BTC/USDT", "15m", _candles(trend="up"))
    if signal.signal.value == "LONG":
        assert signal.stop_loss < signal.entry_price
        assert signal.take_profit > signal.entry_price
