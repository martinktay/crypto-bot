import pandas as pd

from app.schemas.signal import SignalContract
from app.strategies.ema_rsi import EmaRsiStrategy


def test_ema_rsi_returns_contract() -> None:
    candles = pd.DataFrame(
        {
            "ts": list(range(60)),
            "open": [100 + i * 0.1 for i in range(60)],
            "high": [101 + i * 0.1 for i in range(60)],
            "low": [99 + i * 0.1 for i in range(60)],
            "close": [100 + i * 0.1 for i in range(60)],
            "volume": [10_000] * 60,
        }
    )
    signal = EmaRsiStrategy().generate("BTC/USDT", "15m", candles)
    assert isinstance(signal, SignalContract)
    assert signal.symbol == "BTC/USDT"
    assert 0 <= signal.confidence <= 100
    assert signal.quality_score == signal.confidence
    if signal.signal.value == "HOLD":
        assert signal.confidence_audit_ema_bps is None
