import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session
from sqlalchemy import desc, select

from app.core.enums import SignalDirection
from app.core.state import RuntimeState
from app.models.entities import BotSetting, Signal
from app.schemas.signal import SignalContract


class StateRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_settings(self) -> BotSetting:
        from app.core.config import settings

        setting = self.db.execute(select(BotSetting).limit(1)).scalar_one_or_none()
        if not setting:
            setting = BotSetting(
                execution_mode="signal_only",
                paused=False,
                symbols=settings.symbol_list,
                timeframes=settings.timeframe_list,
                strategy=settings.strategy,
            )
            self.db.add(setting)
            self.db.commit()
            self.db.refresh(setting)
        return setting

    def sync_timeframes_and_strategy_from_env(self) -> bool:
        """Align DB ``timeframes`` + ``strategy`` with :mod:`app.core.config` (.env).

        Returns ``True`` if a row was updated. Does not modify ``symbols``.
        """
        from app.core.config import settings
        from app.models.entities import BotSetting

        row = self.db.execute(select(BotSetting).limit(1)).scalar_one_or_none()
        if row is None:
            return False
        target_tfs = list(settings.timeframe_list)
        target_strat = settings.strategy
        changed = False
        if list(row.timeframes) != target_tfs:
            row.timeframes = target_tfs
            changed = True
        if row.strategy != target_strat:
            row.strategy = target_strat
            changed = True
        if changed:
            self.db.commit()
            self.db.refresh(row)
        return changed

    def get_runtime_state_snapshot(self) -> RuntimeState:
        """Hydrate a pure RuntimeState DTO from database rows."""
        setting = self.get_or_create_settings()

        raw_signals = self.db.execute(
            select(Signal).order_by(desc(Signal.timestamp)).limit(10)
        ).scalars().all()
        signals = [
            SignalContract(
                symbol=s.symbol,
                timeframe=s.timeframe,
                signal=s.signal,
                entry_price=s.entry_price,
                stop_loss=s.stop_loss,
                take_profit=s.take_profit,
                confidence=s.confidence,
                order_type=s.order_type,
                reason=s.reason,
                exchange_id=s.exchange_id or "binance",
                timestamp=s.timestamp.replace(tzinfo=timezone.utc),
            )
            for s in raw_signals
        ]

        return RuntimeState(
            paused=setting.paused,
            symbols=list(setting.symbols),
            timeframes=list(setting.timeframes),
            strategy=setting.strategy,
            execution_mode=setting.execution_mode,
            signals=signals,
            recent_outcomes=[],
        )

    def record_signal(self, contract: SignalContract, ai_explanation: str = "") -> int:
        ts = contract.timestamp
        if ts is None:
            ts = datetime.now(timezone.utc)
        sig = Signal(
            symbol=contract.symbol,
            timeframe=contract.timeframe,
            signal=contract.signal,
            entry_price=contract.entry_price,
            stop_loss=contract.stop_loss,
            take_profit=contract.take_profit,
            confidence=contract.confidence,
            order_type=contract.order_type,
            reason=contract.reason,
            ai_explanation=ai_explanation,
            exchange_id=(contract.exchange_id or "binance"),
            timestamp=ts.replace(tzinfo=None),
        )
        self.db.add(sig)
        self.db.commit()
        return sig.id

    def update_mode(self, paused: bool | None = None) -> None:
        setting = self.get_or_create_settings()
        if paused is not None:
            setting.paused = paused
        self.db.commit()

    def update_symbols_timeframes_strategy(self, symbols: list[str] | None = None, timeframes: list[str] | None = None, strategy: str | None = None) -> None:
        setting = self.get_or_create_settings()
        if symbols is not None:
            setting.symbols = symbols
        if timeframes is not None:
            setting.timeframes = timeframes
        if strategy is not None:
            setting.strategy = strategy
        self.db.commit()

    def get_recent_outcomes(self) -> list[dict]:
        """Return recent signals with their *real* tracked outcomes.

        Outcome fields are populated by :meth:`record_signal_outcome` once the
        signal hits TP/SL or expires. Until then, ``outcome_status='pending'``
        and the numeric fields are ``None``.
        """
        raw = self.db.execute(
            select(Signal).order_by(desc(Signal.timestamp)).limit(50)
        ).scalars().all()
        outcomes = []
        for s in raw:
            success: bool | None
            if s.outcome_status == "tp_hit":
                success = True
            elif s.outcome_status in {"sl_hit", "expired"}:
                success = False
            else:
                success = None

            outcomes.append({
                "signal_id": s.id,
                "symbol": s.symbol,
                "timeframe": s.timeframe,
                "strategy": "N/A",
                "signal": s.signal.value,
                "confidence": s.confidence,
                "order_type": s.order_type,
                "exchange_id": s.exchange_id,
                "entry_price": s.entry_price,
                "stop_loss": s.stop_loss,
                "take_profit": s.take_profit,
                "risk_note": s.reason,
                "signal_status": s.outcome_status,
                "ai_explanation": s.ai_explanation,
                "success": success,
                "growth_pct": s.outcome_pnl_percent,
                "max_drawdown": s.outcome_max_drawdown_percent,
                "timestamp": s.timestamp.isoformat() if s.timestamp else None,
                "resolved_at": (
                    s.outcome_resolved_at.isoformat()
                    if s.outcome_resolved_at
                    else None
                ),
            })
        return outcomes

    def list_open_broadcast_signals(self, max_age_hours: int) -> list[Signal]:
        """Return non-HOLD signals whose outcome is still ``pending``."""
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        rows = self.db.execute(
            select(Signal)
            .where(Signal.signal != SignalDirection.HOLD)
            .where(Signal.outcome_status == "pending")
            .where(Signal.timestamp >= cutoff)
            .order_by(Signal.timestamp)
        ).scalars().all()
        return list(rows)

    def record_signal_outcome(
        self,
        signal_id: int,
        outcome_status: str,
        pnl_percent: float | None = None,
        max_drawdown_percent: float | None = None,
    ) -> None:
        """Record the realized outcome of a signal.

        ``outcome_status`` must be one of: ``tp_hit``, ``sl_hit``, ``expired``,
        ``cancelled``, ``pending``.
        """
        from app.models.entities import Signal as SignalModel

        self.db.query(SignalModel).filter(SignalModel.id == signal_id).update({
            "outcome_status": outcome_status,
            "outcome_pnl_percent": pnl_percent,
            "outcome_max_drawdown_percent": max_drawdown_percent,
            "outcome_resolved_at": datetime.now(timezone.utc).replace(tzinfo=None),
        })
        self.db.commit()



    def get_signal_performance_summary(self) -> dict:
        """Calculate signal-level performance KPIs for the dashboard.

        Numbers are derived from *resolved* live signals (``outcome_status``
        in ``{tp_hit, sl_hit, expired}``). When no live outcomes exist yet,
        falls back to backtest history and clearly marks the source.
        """
        from sqlalchemy import func

        from app.models.entities import BacktestHistory, Signal

        total_signals = self.db.query(func.count(Signal.id)).filter(
            Signal.signal != SignalDirection.HOLD
        ).scalar() or 0

        resolved_filter = Signal.outcome_status.in_(
            ("tp_hit", "sl_hit", "expired")
        )
        resolved_count = self.db.query(func.count(Signal.id)).filter(
            resolved_filter
        ).scalar() or 0

        if resolved_count > 0:
            wins = self.db.query(func.count(Signal.id)).filter(
                Signal.outcome_status == "tp_hit"
            ).scalar() or 0
            win_rate = (wins / resolved_count) * 100.0

            avg_pnl = self.db.query(
                func.avg(Signal.outcome_pnl_percent)
            ).filter(resolved_filter).scalar() or 0.0
            max_ae = self.db.query(
                func.avg(Signal.outcome_max_drawdown_percent)
            ).filter(resolved_filter).scalar() or 0.0

            return {
                "total_signals": total_signals,
                "resolved_signals": resolved_count,
                "win_rate": round(float(win_rate), 1),
                "avg_growth": round(float(avg_pnl), 1),
                "max_ae": round(float(max_ae), 1),
                "source": "live",
            }

        avg_win_rate = self.db.query(
            func.avg(BacktestHistory.win_rate)
        ).scalar() or 0.0
        growth = self.db.query(
            func.avg(
                (BacktestHistory.final_balance - BacktestHistory.initial_balance)
                / BacktestHistory.initial_balance
                * 100
            )
        ).scalar() or 0.0
        max_ae = self.db.query(
            func.avg(BacktestHistory.max_drawdown)
        ).scalar() or 0.0

        return {
            "total_signals": total_signals,
            "resolved_signals": 0,
            "win_rate": round(float(avg_win_rate), 1),
            "avg_growth": round(float(growth), 1),
            "max_ae": round(float(max_ae), 1),
            "source": "backtest",
        }

    def ingest_knowledge_document(
        self,
        title: str,
        content: str,
        source_type: str,
        vector: list[float],
        metadata: dict | None = None,
    ) -> int:
        """Insert a knowledge document with its embedding into the vector store."""
        from app.models.entities import KnowledgeDocument, KnowledgeEmbedding
        metadata = metadata or {}
        
        # 1. Create the base document
        doc = KnowledgeDocument(
            title=title,
            content=content,
            source_type=source_type,
            metadata_json=metadata
        )
        self.db.add(doc)
        self.db.flush()  # Get the ID without committing yet

        # 2. Ensure vector dimension matches DB schema (1536)
        if len(vector) != 1536:
            logger.warning("Vector dimension mismatch: %d != 1536. Correcting.", len(vector))
            if len(vector) > 1536:
                vector = vector[:1536]
            else:
                vector = vector + [0.0] * (1536 - len(vector))

        # 3. Create the embedding entry linked to the document
        emb = KnowledgeEmbedding(
            document_id=doc.id,
            embedding=vector
        )
        self.db.add(emb)
        self.db.commit()
        return doc.id

    def ingest_trade_insight(self, lesson: str, vector: list[float], outcome: dict) -> int:
        """Specialized ingestion for trade outcomes that builds a knowledge document."""
        title = f"Lesson: {outcome.get('symbol')} {outcome.get('direction')} Outcome"
        return self.ingest_knowledge_document(
            title=title,
            content=lesson,
            source_type="trade_outcome",
            vector=vector,
            metadata=outcome
        )

    def search_similar_insights(self, query_vector: list[float], limit: int = 3, source_type: str | None = None) -> list[str]:
        """Query nearest knowledge documents matching the query vector context."""
        from app.models.entities import KnowledgeDocument, KnowledgeEmbedding

        dialect = self.db.get_bind().dialect.name
        
        if dialect == "postgresql":
            stmt = (
                select(KnowledgeDocument.content)
                .join(KnowledgeEmbedding, KnowledgeDocument.id == KnowledgeEmbedding.document_id)
            )
            if source_type:
                stmt = stmt.where(KnowledgeDocument.source_type == source_type)
                
            return list(self.db.execute(
                stmt.order_by(KnowledgeEmbedding.embedding.l2_distance(query_vector))
                .limit(limit)
            ).scalars().all())
        else:
            # SQLite fallback: Load all embeddings and calculate L2 distance in Python
            # Note: This is less efficient but works for small-scale local dev
            stmt = select(KnowledgeDocument.content, KnowledgeEmbedding.embedding).join(
                KnowledgeEmbedding, KnowledgeDocument.id == KnowledgeEmbedding.document_id
            )
            if source_type:
                stmt = stmt.where(KnowledgeDocument.source_type == source_type)
            
            results = self.db.execute(stmt).all()
            if not results:
                return []
            
            # Simple L2 distance function
            def l2_dist(v1, v2):
                return sum((x - y) ** 2 for x, y in zip(v1, v2))

            # Sort by distance and return top contents
            sorted_results = sorted(
                results, 
                key=lambda x: l2_dist(x[1] if isinstance(x[1], list) else json.loads(x[1]), query_vector)
            )
            return [content for content, _ in sorted_results[:limit]]

    def count_knowledge_documents(self) -> int:
        """Return the total number of knowledge documents in the database."""
        from app.models.entities import KnowledgeDocument
        return self.db.query(KnowledgeDocument).count()

    def get_knowledge_documents(self, source_type: str | None = None, limit: int = 10) -> list:
        """Fetch a list of knowledge documents from the database."""
        from app.models.entities import KnowledgeDocument
        
        stmt = select(KnowledgeDocument).order_by(desc(KnowledgeDocument.created_at)).limit(limit)
        if source_type:
            stmt = stmt.where(KnowledgeDocument.source_type == source_type)
            
        return list(self.db.execute(stmt).scalars().all())

    def save_backtest_history(self, result: Any) -> int:
        """Save a BacktestResult to the database history."""
        from app.models.entities import BacktestHistory
        
        history = BacktestHistory(
            symbol=result.symbol,
            strategy=result.strategy,
            timeframe=result.timeframe,
            params=result.params or {},
            initial_balance=result.initial_balance,
            final_balance=result.final_balance,
            total_trades=result.total_trades,
            win_rate=result.win_rate,
            max_drawdown=result.max_drawdown_percent,
            sharpe_ratio=result.sharpe_ratio,
            created_at=datetime.utcnow(),
        )
        self.db.add(history)
        self.db.commit()
        self.db.refresh(history)
        return history.id

    def get_backtest_history(self, limit: int = 10) -> list[Any]:
        """Retrieve recent backtest history records."""
        from app.models.entities import BacktestHistory
        return list(
            self.db.execute(
                select(BacktestHistory)
                .order_by(desc(BacktestHistory.created_at))
                .limit(limit)
            ).scalars().all()
        )

    def get_rejected_signals(self, limit: int = 5) -> list[dict]:
        """Fetch recent non-HOLD signals that risk-engine filtered out.

        Filtered = recorded with a non-broadcast outcome status (currently we
        only store ``pending`` / TP-SL outcomes, so this returns recent
        non-HOLD signals as a best-effort filter view).
        """
        rows = self.db.execute(
            select(Signal)
            .where(Signal.signal != SignalDirection.HOLD)
            .order_by(desc(Signal.timestamp))
            .limit(limit)
        ).scalars().all()

        return [
            {
                "symbol": s.symbol,
                "timeframe": s.timeframe,
                "signal": s.signal.value,
                "reason": s.reason,
                "timestamp": s.timestamp,
            }
            for s in rows
        ]
