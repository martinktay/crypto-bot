from datetime import datetime, timedelta, timezone

from app.approval_workflow.service import ApprovalWorkflow
from app.core.enums import SignalDirection
from app.core.state import PendingApproval
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


def test_create_approval_pending() -> None:
    item = ApprovalWorkflow(timeout_minutes=5).create(_signal())
    assert item.status == "pending"
    assert item.approval_id


def test_expired_approval_gets_expired_status() -> None:
    workflow = ApprovalWorkflow(timeout_minutes=5)
    pending = PendingApproval(
        approval_id="x",
        signal=_signal(),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    outcome = workflow.decide(pending, approved=True)
    assert outcome.status == "expired"
