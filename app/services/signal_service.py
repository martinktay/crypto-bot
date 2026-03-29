from __future__ import annotations

import pandas as pd

from app.approval_workflow.service import ApprovalWorkflow
from app.core.enums import TradingMode
from app.core.state import PendingApproval, RuntimeState
from app.execution.engine import ExecutionEngine
from app.knowledge_base.reasoning import ReasoningEngine
from app.market_data.provider import MarketDataProvider
from app.risk_management.engine import RiskEngine
from app.strategies.ema_rsi import EmaRsiStrategy


class SignalPipeline:
    def __init__(self) -> None:
        self.market_data = MarketDataProvider()
        self.strategy = EmaRsiStrategy()
        self.risk_engine = RiskEngine()
        self.execution_engine = ExecutionEngine()
        self.reasoning_engine = ReasoningEngine()
        self.approval_workflow = ApprovalWorkflow(timeout_minutes=5)

    def run_cycle(self, state: RuntimeState) -> list[dict]:
        outcomes: list[dict] = []

        for symbol in state.symbols:
            for timeframe in state.timeframes:
                raw = self.market_data.fetch_ohlcv(symbol, timeframe)
                df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
                signal = self.strategy.generate(symbol, timeframe, df)
                ai_explanation = self.reasoning_engine.explain(signal, context="")
                state.signals.insert(0, signal)
                state.signals = state.signals[:100]

                approved, risk_note = self.risk_engine.validate_signal(signal)
                outcome = {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "signal": signal.signal,
                    "confidence": signal.confidence,
                    "risk_note": risk_note,
                    "ai_explanation": ai_explanation,
                }

                if state.mode == TradingMode.MANUAL_APPROVAL and approved:
                    pending: PendingApproval = self.approval_workflow.create(signal)
                    state.approvals[pending.approval_id] = pending
                    outcome["approval_id"] = pending.approval_id
                    outcome["execution"] = "waiting_manual_approval"
                else:
                    execution = self.execution_engine.execute(state.mode, signal, approved=approved)
                    outcome["execution"] = execution.details
                    if execution.accepted:
                        state.trades.insert(
                            0,
                            {
                                "symbol": signal.symbol,
                                "entry": signal.entry_price,
                                "mode": state.mode.value,
                                "timestamp": signal.timestamp.isoformat(),
                            },
                        )
                        state.trades = state.trades[:100]
                outcomes.append(outcome)

        return outcomes

    def apply_approval_decision(self, state: RuntimeState, approval_id: str, approved: bool) -> dict:
        pending = state.approvals.get(approval_id)
        if pending is None:
            return {"result": "not_found"}

        decision = self.approval_workflow.decide(pending, approved)
        if decision.status != "approved":
            return {"result": decision.status, "approval_id": approval_id}

        execution = self.execution_engine.execute(state.mode, decision.signal, approved=True)
        if execution.accepted:
            state.trades.insert(
                0,
                {
                    "symbol": decision.signal.symbol,
                    "entry": decision.signal.entry_price,
                    "mode": state.mode.value,
                    "timestamp": decision.signal.timestamp.isoformat(),
                },
            )
        return {
            "result": decision.status,
            "approval_id": approval_id,
            "execution": execution.details,
            "trade": decision.signal.model_dump(mode="json"),
        }
