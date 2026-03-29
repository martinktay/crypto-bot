"""Core signal pipeline orchestration for MVP trading flow."""

from __future__ import annotations

import logging

import pandas as pd

from app.approval_workflow.service import ApprovalWorkflow
from app.core.enums import TradeStatus, TradingMode
from app.core.state import PendingApproval, RuntimeState
from app.db.session import SessionLocal
from app.execution.engine import ExecutionEngine
from app.knowledge_base.memory import StrategyDocs, TradeMemory
from app.knowledge_base.reasoning import ReasoningEngine
from app.market_data.provider import MarketDataProvider
from app.monitoring.metrics import signals_generated, trade_rejections
from app.risk_management.engine import RiskEngine
from app.services.repository import TradeRepository, safe_commit
from app.strategies.registry import build_strategy
from app.telegram_bot.service import TelegramNotifier

logger = logging.getLogger(__name__)


class SignalPipeline:
    def __init__(self) -> None:
        self.market_data = MarketDataProvider()
        self.risk_engine = RiskEngine()
        self.execution_engine = ExecutionEngine()
        self.reasoning_engine = ReasoningEngine()
        self.approval_workflow = ApprovalWorkflow(timeout_minutes=5)
        self.trade_memory = TradeMemory()
        self.strategy_docs = StrategyDocs()
        self.telegram = TelegramNotifier()

    def _persist_signal_and_trade(self, signal, ai_explanation: str, trade_payload: dict | None = None) -> None:
        db = SessionLocal()
        try:
            repo = TradeRepository(db)
            signal_row = repo.create_signal(signal, ai_explanation)
            if trade_payload is not None:
                trade = repo.create_trade(signal_row.id, trade_payload)
                repo.create_position(trade.id, trade_payload["symbol"], trade_payload.get("quantity", 0.0), trade_payload["entry"])
            result = safe_commit(db)
            if not result.ok:
                logger.warning("Persistence issue: %s", result.detail)
        finally:
            db.close()

    def run_cycle(self, state: RuntimeState) -> list[dict]:
        outcomes: list[dict] = []
        strategy = build_strategy(state.strategy)

        # MVP runs a simple nested loop over configured symbols/timeframes.
        for symbol in state.symbols:
            for timeframe in state.timeframes:
                raw = self.market_data.fetch_ohlcv(symbol, timeframe)
                df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
                signal = strategy.generate(symbol, timeframe, df)

                docs = self.strategy_docs.relevant_docs(state)
                similar = self.trade_memory.similar_trades(state, signal)
                context = (
                    f"docs={'; '.join([d['title'] for d in docs])}; "
                    f"similar_trades={len(similar)}"
                )
                ai_explanation = self.reasoning_engine.explain(signal, context=context)

                approved_signal, risk_note = self.risk_engine.validate_signal(signal)
                approved_limits, limits_note = self.risk_engine.validate_runtime_limits(state, signal)
                approved = approved_signal and approved_limits

                outcome = {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "strategy": strategy.name,
                    "signal": signal.signal,
                    "confidence": signal.confidence,
                    "risk_note": risk_note,
                    "limits_note": limits_note,
                    "knowledge_context": context,
                }

                state.signals.insert(0, signal)
                state.signals = state.signals[:100]
                signals_generated.inc()

                # Manual approval mode: queue decision before executing paper trade.
                if state.mode == TradingMode.MANUAL_APPROVAL and approved:
                    pending: PendingApproval = self.approval_workflow.create(signal)
                    state.approvals[pending.approval_id] = pending
                    outcome["approval_id"] = pending.approval_id
                    outcome["execution"] = "waiting_manual_approval"
                    self._persist_signal_and_trade(signal, ai_explanation)
                else:
                    execution = self.execution_engine.execute(state.mode, signal, approved=approved)
                    outcome["execution"] = execution.details
                    if execution.accepted:
                        trade_payload = {
                            "symbol": signal.symbol,
                            "timeframe": signal.timeframe,
                            "entry": signal.entry_price,
                            "signal": signal.signal.value,
                            "mode": state.mode,
                            "timestamp": signal.timestamp.isoformat(),
                            "status": TradeStatus.OPEN,
                            "quantity": 0.0,
                        }
                        state.trades.insert(0, trade_payload)
                        state.trades = state.trades[:200]
                        self._persist_signal_and_trade(signal, ai_explanation, trade_payload=trade_payload)
                    else:
                        trade_rejections.inc()
                        self._persist_signal_and_trade(signal, ai_explanation)

                # Always attempt Telegram delivery for visibility of generated signals.
                message = self.telegram.build_signal_message(signal, ai_explanation, state.mode)
                outcome["telegram_delivered"] = self.telegram.send_message(message)
                outcomes.append(outcome)

        state.recent_outcomes = outcomes[:50]
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
            trade_payload = {
                "symbol": decision.signal.symbol,
                "timeframe": decision.signal.timeframe,
                "entry": decision.signal.entry_price,
                "signal": decision.signal.signal.value,
                "mode": state.mode,
                "timestamp": decision.signal.timestamp.isoformat(),
                "status": TradeStatus.OPEN,
                "quantity": 0.0,
            }
            state.trades.insert(0, trade_payload)
            self._persist_signal_and_trade(decision.signal, "approved manual execution", trade_payload=trade_payload)
        else:
            trade_rejections.inc()
        return {
            "result": decision.status,
            "approval_id": approval_id,
            "execution": execution.details,
            "trade": decision.signal.model_dump(mode="json"),
        }
