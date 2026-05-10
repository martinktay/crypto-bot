"""SignalContract quality vs audit fields."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.enums import SignalDirection
from app.schemas.signal import SignalContract


def test_legacy_confidence_only_populates_quality() -> None:
    s = SignalContract(
        symbol="ETH/USDT",
        timeframe="1h",
        signal=SignalDirection.LONG,
        entry_price=1.0,
        stop_loss=0.9,
        take_profit=1.1,
        confidence=88.0,
        reason="test",
        timestamp=datetime.now(timezone.utc),
    )
    assert s.quality_score == 88.0
    assert s.confidence == 88.0
    assert s.confidence_audit_ema_bps is None


def test_hold_clears_scores() -> None:
    s = SignalContract(
        symbol="BTC/USDT",
        timeframe="15m",
        signal=SignalDirection.HOLD,
        entry_price=1.0,
        stop_loss=1.0,
        take_profit=1.0,
        confidence=99.0,
        reason="no trade",
        timestamp=datetime.now(timezone.utc),
    )
    assert s.quality_score == 0.0
    assert s.confidence == 0.0
    assert s.confidence_audit_ema_bps is None


def test_explicit_quality_and_audit() -> None:
    s = SignalContract(
        symbol="BTC/USDT",
        timeframe="15m",
        signal=SignalDirection.SHORT,
        entry_price=100.0,
        stop_loss=102.0,
        take_profit=96.0,
        quality_score=71.0,
        confidence_audit_ema_bps=44.0,
        confidence=71.0,
        reason="cross",
        timestamp=datetime.now(timezone.utc),
    )
    assert s.quality_score == 71.0
    assert s.confidence_audit_ema_bps == 44.0
    assert s.confidence == 71.0
