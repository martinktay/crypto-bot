from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import SignalDirection
from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(32), default="admin")


class BotSetting(Base):
    __tablename__ = "bot_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    execution_mode: Mapped[str] = mapped_column(
        String(20), default="signal_only"
    )
    paused: Mapped[bool] = mapped_column(default=False)
    symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    timeframes: Mapped[list[str]] = mapped_column(JSON, default=list)
    strategy: Mapped[str] = mapped_column(String(100), default="ema_rsi")


class Signal(Base):
    __tablename__ = "signals"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(80), index=True)
    timeframe: Mapped[str] = mapped_column(String(10), index=True)
    signal: Mapped[SignalDirection] = mapped_column(Enum(SignalDirection), index=True)
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    order_type: Mapped[str] = mapped_column(String(20), default="LIMIT")
    reason: Mapped[str] = mapped_column(Text)
    ai_explanation: Mapped[str] = mapped_column(Text, default="")
    atr_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    exchange_id: Mapped[str] = mapped_column(String(32), default="binance", index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    outcome_status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )
    outcome_pnl_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome_max_drawdown_percent: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    outcome_resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


from app.db.types import VectorType

class KnowledgeEmbedding(Base):
    __tablename__ = "knowledge_embeddings"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    embedding: Mapped[list[float]] = mapped_column(VectorType(1536))


class BacktestHistory(Base):
    __tablename__ = "backtest_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(80), index=True)
    strategy: Mapped[str] = mapped_column(String(100), index=True)
    timeframe: Mapped[str] = mapped_column(String(10))
    params: Mapped[dict] = mapped_column(JSON, default={})
    initial_balance: Mapped[float] = mapped_column(Float)
    final_balance: Mapped[float] = mapped_column(Float)
    total_trades: Mapped[int] = mapped_column(Integer)
    win_rate: Mapped[float] = mapped_column(Float)
    max_drawdown: Mapped[float] = mapped_column(Float)
    sharpe_ratio: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


Index("idx_signal_symbol_timeframe_timestamp", Signal.symbol, Signal.timeframe, Signal.timestamp)
