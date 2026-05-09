from datetime import datetime, timedelta, timezone

from app.core.enums import SignalDirection
from app.core.state import RuntimeState
from app.risk_management.engine import RiskEngine
from app.schemas.signal import SignalContract


def _signal() -> SignalContract:
    return SignalContract(
        symbol="BTC/USDT",
        timeframe="15m",
        signal=SignalDirection.LONG,
        entry_price=100,
        stop_loss=99,
        take_profit=102,
        confidence=75,
        reason="test",
        timestamp=datetime.now(timezone.utc),
    )


def test_cooldown_blocks_duplicate_signal() -> None:
    state = RuntimeState()
    previous = _signal()
    previous.timestamp = datetime.now(timezone.utc) - timedelta(minutes=1)
    state.signals.append(previous)

    ok, note = RiskEngine().validate_runtime_limits(state, _signal())
    assert not ok
    assert "cooldown" in note.lower()
