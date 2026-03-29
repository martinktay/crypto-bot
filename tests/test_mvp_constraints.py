from datetime import datetime, timezone

import pytest

from app.core.enums import SignalDirection, TradingMode
from app.core.startup import validate_runtime_settings
from app.execution.engine import ExecutionEngine
from app.schemas.signal import SignalContract


class _SettingsStub:
    default_mode = TradingMode.AUTO_TRADE_LIVE
    symbol_list = ["BTC/USDT"]
    timeframe_list = ["15m"]


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


def test_startup_rejects_auto_live_mode() -> None:
    with pytest.raises(ValueError):
        validate_runtime_settings(_SettingsStub())


def test_execution_rejects_live_mode() -> None:
    result = ExecutionEngine().execute(TradingMode.AUTO_TRADE_LIVE, _signal(), approved=True)
    assert not result.accepted
    assert "disabled" in result.details
