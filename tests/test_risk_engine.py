from datetime import datetime, timezone

from app.core.enums import SignalDirection
from app.risk_management.engine import RiskEngine
from app.schemas.signal import SignalContract


def _build_signal(signal: SignalDirection, entry: float, stop: float, take: float) -> SignalContract:
    return SignalContract(
        symbol="BTC/USDT",
        timeframe="15m",
        signal=signal,
        entry_price=entry,
        stop_loss=stop,
        take_profit=take,
        confidence=70,
        reason="test",
        timestamp=datetime.now(timezone.utc),
    )


def test_reject_hold_signal() -> None:
    ok, reason = RiskEngine().validate_signal(_build_signal(SignalDirection.HOLD, 100, 100, 100))
    assert not ok
    assert "HOLD" in reason


def test_accept_valid_rr() -> None:
    ok, _ = RiskEngine().validate_signal(_build_signal(SignalDirection.LONG, 100, 99, 102))
    assert ok
