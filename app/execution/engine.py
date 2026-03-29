from dataclasses import dataclass

from app.core.config import settings
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
            return ExecutionResult(True, mode, "Signal sent only")

        if mode == TradingMode.MANUAL_APPROVAL and not approved:
            return ExecutionResult(False, mode, "Manual approval required")

        if mode == TradingMode.PAPER_TRADING or mode == TradingMode.MANUAL_APPROVAL:
            slippage = signal.entry_price * 0.0005
            fee = signal.entry_price * 0.001
            return ExecutionResult(True, mode, f"Paper trade executed with slippage={slippage:.2f}, fee={fee:.2f}")

        if not settings.enable_live_trading:
            return ExecutionResult(False, mode, "Live execution blocked: ENABLE_LIVE_TRADING=false")

        return ExecutionResult(False, mode, "Live execution adapter not configured in MVP")
