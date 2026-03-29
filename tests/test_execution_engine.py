from datetime import datetime, timezone

from app.core.enums import SignalDirection, TradingMode
from app.execution.engine import ExecutionEngine
from app.schemas.signal import SignalContract


def _signal() -> SignalContract:
    return SignalContract(
        symbol="BTC/USDT",
        timeframe="15m",
        signal=SignalDirection.LONG,
        entry_price=100,
        stop_loss=99,
        take_profit=102,
        confidence=80,
        reason="test",
        timestamp=datetime.now(timezone.utc),
    )


def test_manual_mode_blocks_without_approval() -> None:
    result = ExecutionEngine().execute(TradingMode.MANUAL_APPROVAL, _signal(), approved=False)
    assert not result.accepted
    assert "required" in result.details
