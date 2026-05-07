import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session
from sqlalchemy import desc, select

from app.core.config import settings
from app.core.enums import ApprovalMode, SignalDirection
from app.core.state import PendingApproval as PendingApprovalContract
from app.core.state import RuntimeState
from app.models.entities import BotSetting, PendingApproval, Signal
from app.schemas.signal import SignalContract


class StateRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_settings(self) -> BotSetting:
        setting = self.db.execute(select(BotSetting).limit(1)).scalar_one_or_none()
        if not setting:
            setting = BotSetting(
                execution_mode="signal_only",
                approval_mode=settings.approval_mode,
                paused=False,
                symbols=settings.symbol_list,
                timeframes=settings.timeframe_list,
                strategy=settings.strategy,
            )
            self.db.add(setting)
            self.db.commit()
            self.db.refresh(setting)
        return setting

    def get_runtime_state_snapshot(self) -> RuntimeState:
        """Hydrate a pure RuntimeState DTO from database rows."""
        setting = self.get_or_create_settings()

        # Load recent signals
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
                timestamp=s.timestamp.replace(tzinfo=timezone.utc),
            )
            for s in raw_signals
        ]

        # Load active approvals
        raw_approvals = self.db.execute(
            select(PendingApproval, Signal)
            .join(Signal, PendingApproval.signal_id == Signal.id)
            .where(PendingApproval.status == "pending")
        ).all()
        approvals = {}
        for apprv, sig in raw_approvals:
            approvals[apprv.approval_id] = PendingApprovalContract(
                approval_id=apprv.approval_id,
                expires_at=apprv.expires_at.replace(tzinfo=timezone.utc),
                status=apprv.status,
                signal=SignalContract(
                    symbol=sig.symbol,
                    timeframe=sig.timeframe,
                    signal=sig.signal,
                    entry_price=sig.entry_price,
                    stop_loss=sig.stop_loss,
                    take_profit=sig.take_profit,
                    confidence=sig.confidence,
                    order_type=sig.order_type,
                    reason=sig.reason,
                    timestamp=sig.timestamp.replace(tzinfo=timezone.utc),
                )
            )

        return RuntimeState(
            approval_mode=setting.approval_mode,
            paused=setting.paused,
            symbols=list(setting.symbols),
            timeframes=list(setting.timeframes),
            strategy=setting.strategy,
            execution_mode=setting.execution_mode,
            signals=signals,
            approvals=approvals,
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
            timestamp=ts.replace(tzinfo=None),
        )
        self.db.add(sig)
        self.db.commit()
        return sig.id

    def create_pending_approval(self, approval_id: str, signal_id: int, expires_at: datetime) -> None:
        apprv = PendingApproval(
            approval_id=approval_id,
            signal_id=signal_id,
            expires_at=expires_at.replace(tzinfo=None),
            status="pending"
        )
        self.db.add(apprv)
        self.db.commit()

    def get_pending_approval(self, approval_id: str) -> PendingApprovalContract | None:
        row = self.db.execute(
            select(PendingApproval, Signal)
            .join(Signal, PendingApproval.signal_id == Signal.id)
            .where(PendingApproval.approval_id == approval_id)
        ).first()

        if not row:
            return None

        apprv, sig = row
        return PendingApprovalContract(
            approval_id=apprv.approval_id,
            expires_at=apprv.expires_at.replace(tzinfo=timezone.utc),
            status=apprv.status,
            signal=SignalContract(
                symbol=sig.symbol,
                timeframe=sig.timeframe,
                signal=sig.signal,
                entry_price=sig.entry_price,
                stop_loss=sig.stop_loss,
                take_profit=sig.take_profit,
                confidence=sig.confidence,
                order_type=sig.order_type,
                reason=sig.reason,
                timestamp=sig.timestamp.replace(tzinfo=timezone.utc),
            )
        )

    def resolve_approval(self, approval_id: str, status: str) -> int:
        """Atomically transition a pending approval to a terminal status.

        Only rows where ``status == 'pending'`` are updated. Returns the
        number of affected rows so callers can detect replays.
        """
        affected = (
            self.db.query(PendingApproval)
            .filter(
                PendingApproval.approval_id == approval_id,
                PendingApproval.status == "pending",
            )
            .update({"status": status})
        )
        self.db.commit()
        return int(affected)

    def update_mode(self, approval_mode: ApprovalMode | None = None, paused: bool | None = None) -> None:
        setting = self.get_or_create_settings()
        if approval_mode:
            setting.approval_mode = approval_mode
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
                "symbol": s.symbol,
                "timeframe": s.timeframe,
                "strategy": "N/A",
                "signal": s.signal.value,
                "confidence": s.confidence,
                "order_type": s.order_type,
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
        """Return non-HOLD signals whose outcome is still ``pending``.

        Excludes signals whose linked approval was *rejected* (those were
        never broadcast so realized PnL is meaningless).
        """
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        rejected_signal_ids = select(PendingApproval.signal_id).where(
            PendingApproval.status == "rejected"
        )
        rows = self.db.execute(
            select(Signal)
            .where(Signal.signal != SignalDirection.HOLD)
            .where(Signal.outcome_status == "pending")
            .where(Signal.timestamp >= cutoff)
            .where(Signal.id.not_in(rejected_signal_ids))
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
        """Fetch signals that were generated but not attached to an approval."""
        from app.models.entities import PendingApproval
        
        # Signals that are NOT HOLD and have no PendingApproval
        sub_apprv = select(PendingApproval.signal_id)
        
        rows = self.db.execute(
            select(Signal)
            .where(Signal.signal != SignalDirection.HOLD)
            .where(Signal.id.not_in(sub_apprv))
            .order_by(desc(Signal.timestamp))
            .limit(limit)
        ).scalars().all()
        
        return [
            {
                "symbol": s.symbol,
                "timeframe": s.timeframe,
                "signal": s.signal.value,
                "reason": s.reason,
                "timestamp": s.timestamp
            }
            for s in rows
        ]
