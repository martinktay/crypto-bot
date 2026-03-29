"""In-memory knowledge helpers for trade memory and strategy documents."""

from __future__ import annotations

from app.core.state import RuntimeState
from app.schemas.signal import SignalContract


class TradeMemory:
    def similar_trades(self, state: RuntimeState, signal: SignalContract, limit: int = 3) -> list[dict]:
        matches = [
            t
            for t in state.trades
            if t.get("symbol") == signal.symbol and t.get("timeframe") == signal.timeframe
        ]
        return matches[:limit]


class StrategyDocs:
    def ensure_seed_docs(self, state: RuntimeState) -> None:
        if state.strategy_documents:
            return
        state.strategy_documents = [
            {
                "title": "EMA RSI Playbook",
                "content": "Take LONG when EMA12 > EMA26 and RSI below 70; avoid overextended entries.",
            },
            {
                "title": "Risk Rules",
                "content": "Never bypass stop-loss. Reject setups with poor risk-reward.",
            },
        ]

    def relevant_docs(self, state: RuntimeState, limit: int = 2) -> list[dict]:
        self.ensure_seed_docs(state)
        return state.strategy_documents[:limit]
