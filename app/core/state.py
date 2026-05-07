from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.core.enums import ApprovalMode
from app.schemas.signal import SignalContract


@dataclass
class PendingApproval:
    approval_id: str
    signal: SignalContract
    expires_at: datetime
    status: str = "pending"


@dataclass
class RuntimeState:
    approval_mode: ApprovalMode
    paused: bool = False
    symbols: list[str] = field(default_factory=lambda: ["BTC/USDT"])
    timeframes: list[str] = field(default_factory=lambda: ["15m"])
    strategy: str = "ema_rsi"
    execution_mode: str = "signal_only"
    paper_balance: float = 0.0
    daily_pnl: float = 0.0
    signals: list[SignalContract] = field(default_factory=list)
    approvals: dict[str, PendingApproval] = field(default_factory=dict)
    recent_outcomes: list[dict] = field(default_factory=list)
