"""Execution engine supporting signal-only/manual/paper paths for MVP."""

from dataclasses import dataclass

from app.core.enums import TradingMode
from app.schemas.signal import SignalContract


@dataclass
class ExecutionResult:
    accepted: bool
    mode: TradingMode
    details: str


class ExecutionEngine:
    def execute(self, mode: TradingMode, signal: SignalContract, approved: bool = True) -> ExecutionResult:
        if mode == TradingMode.SIGNAL_ONLY:
            return ExecutionResult(True, mode, "Signal delivered only")

        if mode == TradingMode.MANUAL_APPROVAL and not approved:
            return ExecutionResult(False, mode, "Manual approval required")

        if mode in {TradingMode.PAPER_TRADING, TradingMode.MANUAL_APPROVAL}:
            slippage = signal.entry_price * 0.0005
            fee = signal.entry_price * 0.001
            return ExecutionResult(True, mode, f"Paper trade executed with slippage={slippage:.2f}, fee={fee:.2f}")

        return ExecutionResult(False, mode, "Live trading is intentionally disabled in this MVP")
