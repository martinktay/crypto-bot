from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.core.state import PendingApproval
from app.schemas.signal import SignalContract


class ApprovalWorkflow:
    def __init__(self, timeout_minutes: int = 5):
        self.timeout_minutes = timeout_minutes

    def expires_at(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(minutes=self.timeout_minutes)

    def create(self, signal: SignalContract) -> PendingApproval:
        return PendingApproval(
            approval_id=str(uuid4()),
            signal=signal,
            expires_at=self.expires_at(),
        )

    def decide(self, approval: PendingApproval, approved: bool) -> PendingApproval:
        now = datetime.now(timezone.utc)
        if approval.expires_at < now:
            approval.status = "expired"
            return approval
        approval.status = "approved" if approved else "rejected"
        return approval
