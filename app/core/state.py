from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.signal import SignalContract


@dataclass
class RuntimeState:
    paused: bool = False
    symbols: list[str] = field(default_factory=lambda: ["BTC/USDT"])
    timeframes: list[str] = field(default_factory=lambda: ["15m"])
    strategy: str = "ema_rsi"
    execution_mode: str = "signal_only"
    signals: list[SignalContract] = field(default_factory=list)
    recent_outcomes: list[dict] = field(default_factory=list)
