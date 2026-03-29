"""Persistence repositories for signals, trades, and approvals."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Position, Signal, Trade
from app.schemas.signal import SignalContract


@dataclass
class PersistenceResult:
    ok: bool
    detail: str


class TradeRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_signal(self, signal: SignalContract, ai_explanation: str) -> Signal:
        entity = Signal(
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            signal=signal.signal,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            confidence=signal.confidence,
            reason=signal.reason,
            ai_explanation=ai_explanation,
            timestamp=signal.timestamp,
        )
        self.db.add(entity)
        self.db.flush()
        return entity

    def create_trade(self, signal_id: int, trade_payload: dict) -> Trade:
        entity = Trade(
            signal_id=signal_id,
            symbol=trade_payload["symbol"],
            mode=trade_payload["mode"],
            status=trade_payload.get("status", "open"),
            quantity=trade_payload.get("quantity", 0.0),
            entry_price=trade_payload["entry"],
            metadata_json=trade_payload,
        )
        self.db.add(entity)
        self.db.flush()
        return entity

    def create_position(self, trade_id: int, symbol: str, quantity: float, avg_price: float) -> Position:
        entity = Position(
            trade_id=trade_id,
            symbol=symbol,
            quantity=quantity,
            avg_price=avg_price,
            status="open",
        )
        self.db.add(entity)
        self.db.flush()
        return entity

    def recent_trades(self, symbol: str, timeframe: str, limit: int = 10) -> list[Trade]:
        stmt = (
            select(Trade)
            .where(Trade.symbol == symbol)
            .order_by(Trade.created_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())


def safe_commit(db: Session) -> PersistenceResult:
    try:
        db.commit()
        return PersistenceResult(True, "committed")
    except Exception as exc:
        db.rollback()
        return PersistenceResult(False, f"rollback due to: {exc}")
