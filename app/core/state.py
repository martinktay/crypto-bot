from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.core.enums import TradingMode
from app.schemas.signal import SignalContract


@dataclass
class PendingApproval:
    approval_id: str
    signal: SignalContract
    expires_at: datetime
    status: str = "pending"


@dataclass
class RuntimeState:
    mode: TradingMode
    paused: bool = False
    symbols: list[str] = field(default_factory=lambda: ["BTC/USDT"])
    timeframes: list[str] = field(default_factory=lambda: ["15m"])
    strategy: str = "ema_rsi"
    signals: list[SignalContract] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    positions: list[dict] = field(default_factory=list)
    approvals: dict[str, PendingApproval] = field(default_factory=dict)


runtime_state: RuntimeState | None = None


def init_runtime_state(mode: TradingMode, symbols: list[str], timeframes: list[str]) -> RuntimeState:
    global runtime_state
    runtime_state = RuntimeState(mode=mode, symbols=symbols, timeframes=timeframes)
    return runtime_state


def get_runtime_state() -> RuntimeState:
    if runtime_state is None:
        raise RuntimeError("Runtime state not initialized")
    return runtime_state
