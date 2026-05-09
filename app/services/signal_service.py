from __future__ import annotations

import logging
from typing import Any, Callable

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import SignalDirection
from app.db.repository import StateRepository
from app.knowledge_base.embeddings import EmbeddingProvider
from app.knowledge_base.reasoning import ReasoningEngine
from app.knowledge_base.retrieval import Retriever
from app.market_data.provider import MarketDataProvider
from app.market_data.sentiment import get_sentiment_provider
from app.risk_management.engine import RiskEngine
from app.schemas.signal import SignalContract
from app.strategies.registry import build_strategy
from app.services.tradingagents_review import TradingAgentsReviewer

logger = logging.getLogger(__name__)


class SignalPipeline:
    def __init__(self) -> None:
        self.market_data = MarketDataProvider()
        self.risk_engine = RiskEngine()
        self.reasoning_engine = ReasoningEngine()
        self.embedder = EmbeddingProvider()
        self.reviewer = TradingAgentsReviewer()
        self.sentiment = get_sentiment_provider()
        self._notifier: Callable[..., Any] | None = None

    def set_notifier(self, notifier: Callable[..., Any]) -> None:
        """Register a notification callback for signal events."""
        self._notifier = notifier

    def run_cycle(self, db: Session) -> list[dict]:
        repo = StateRepository(db)
        state = repo.get_runtime_state_snapshot()

        outcomes: list[dict] = []
        strategy = build_strategy(state.strategy)

        if state.paused:
            logger.info("Bot is paused, skipping cycle.")
            return []

        for symbol in state.symbols:
            for timeframe in state.timeframes:
                try:
                    raw = self.market_data.fetch_ohlcv(symbol, timeframe)
                except Exception as exc:
                    logger.error("Failed to fetch %s %s: %s", symbol, timeframe, exc)
                    continue

                df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
                if df.empty:
                    logger.warning("Empty market data for %s %s, skipping", symbol, timeframe)
                    continue

                # Drop the in-progress bar — strategies must only see closed candles.
                if len(df) > 1:
                    df = df.iloc[:-1].reset_index(drop=True)
                if df.empty:
                    continue

                higher_tf_df = self._fetch_higher_tf(symbol, timeframe)
                strategy_params: dict[str, Any] = {}
                if higher_tf_df is not None:
                    strategy_params["higher_tf_candles"] = higher_tf_df

                signal = strategy.generate(symbol, timeframe, df, strategy_params or None)
                signal = self._apply_sentiment(signal)

                # AI explanation + RAG retrieval are skipped for HOLD signals when
                # SKIP_REASONING_ON_HOLD is enabled (default). HOLD signals are
                # never broadcast, so the explanation would be dead weight that
                # costs a chat-completion + an embedding call.
                context_string = ""
                ai_explanation = ""
                should_explain = not (
                    settings.skip_reasoning_on_hold
                    and signal.signal == SignalDirection.HOLD
                )
                if should_explain:
                    try:
                        query = (
                            f"Trading {signal.symbol} on {signal.timeframe} "
                            f"as {signal.signal.value}. {signal.reason}"
                        )
                        retriever = Retriever(db, self.embedder)
                        insights = retriever.get_relevant_context(query, limit=3)
                        if insights:
                            context_string = (
                                "Past applicable lessons & strategy insights:\n"
                                + "\n".join(f"- {i}" for i in insights)
                            )
                    except Exception as exc:
                        logger.error(
                            "Failed to query similar insights: %s", exc.__class__.__name__
                        )

                    ai_explanation = self.reasoning_engine.explain(signal, context=context_string)
                signal.ai_explanation = ai_explanation

                # Risk Validation
                approved_signal, risk_note = self.risk_engine.validate_signal(signal)
                approved_limits, limits_note = self.risk_engine.validate_runtime_limits(state, signal)
                
                is_approved = approved_signal and approved_limits

                # --- TradingAgents Review (Mode A + Mode B) ---
                review = None
                if (
                    self.reviewer.enabled
                    and signal.signal != SignalDirection.HOLD
                    and (self.reviewer.mode_a or self.reviewer.mode_b)
                ):
                    review = self.reviewer.review(
                        signal=signal,
                        risk_note=risk_note,
                        limits_note=limits_note,
                        context=context_string,
                    )
                    if review and self.reviewer.mode_a:
                        signal.ai_explanation = (signal.ai_explanation or "") + self.reviewer.format_for_explanation(review)
                
                # Record in DB (Audit trail)
                signal_id = repo.record_signal(signal, ai_explanation=signal.ai_explanation or ai_explanation)
                
                outcome = {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "signal": signal.signal.value,
                    "price": signal.entry_price,
                    "timestamp": signal.timestamp.isoformat() if signal.timestamp else None,
                    "risk_analysis": risk_note,
                    "limits_analysis": limits_note
                }
                if review:
                    outcome["agent_score"] = review.score
                    outcome["agent_decision"] = review.decision
                    outcome["agent_critique"] = review.critique

                # Mode B gate (only after passing deterministic risk checks)
                if is_approved and review and self.reviewer.mode_b:
                    allowed, gate_reason = self.reviewer.gate(review)
                    if not allowed:
                        is_approved = False
                        outcome["agent_gate"] = gate_reason
                        outcome["signal_status"] = f"rejected_by_agent: {gate_reason}"

                # HOLD is the normal "no trade this bar" state — no channels, no "rejection".
                if signal.signal == SignalDirection.HOLD:
                    outcome["signal_status"] = "hold"
                    outcomes.append(outcome)
                    continue

                if not is_approved:
                    if not str(outcome.get("signal_status", "")).startswith("rejected_by_agent"):
                        outcome["signal_status"] = f"rejected: {risk_note}; {limits_note}"
                    logger.info("Signal filtered for %s: %s", symbol, outcome["signal_status"])
                    outcomes.append(outcome)
                    continue

                outcome["signal_status"] = "Signal Broadcast"
                self._notify("signal", signal=signal, outcome=outcome, state=state)
                outcomes.append(outcome)

        return outcomes

    def _apply_sentiment(self, signal: SignalContract) -> SignalContract:
        """Down-weight confidence when news sentiment opposes the signal.

        This is intentionally a tie-breaker, not a gate: a strong opposing
        sentiment subtracts ``sentiment_confidence_penalty`` from confidence
        (clamped to >= 0) and tags the reason. HOLD signals are untouched.
        """
        if signal.signal == SignalDirection.HOLD or not self.sentiment.enabled:
            return signal
        try:
            score, n_posts = self.sentiment.score(signal.symbol)
        except Exception as exc:
            logger.warning("Sentiment lookup failed: %s", exc.__class__.__name__)
            return signal
        if n_posts < settings.sentiment_min_posts:
            return signal

        threshold = settings.sentiment_block_threshold
        opposes = (
            signal.signal == SignalDirection.LONG and score <= -threshold
        ) or (
            signal.signal == SignalDirection.SHORT and score >= threshold
        )
        if not opposes:
            return signal

        new_conf = max(0.0, signal.confidence - settings.sentiment_confidence_penalty)
        signal.confidence = new_conf
        signal.reason = (
            f"{signal.reason}; sentiment opposing ({score:+.2f}, n={n_posts})"
        )
        return signal

    def _fetch_higher_tf(self, symbol: str, base_timeframe: str) -> pd.DataFrame | None:
        """Fetch higher-timeframe candles for trend confirmation.

        Returns ``None`` when the higher-TF feature is disabled, when no
        mapping exists for ``base_timeframe``, or when the fetch fails. Drops
        the in-progress last bar before returning.
        """
        higher_tf = settings.higher_timeframe_for(base_timeframe)
        if not higher_tf:
            return None
        try:
            raw = self.market_data.fetch_ohlcv(
                symbol, higher_tf, limit=settings.higher_timeframe_lookback
            )
        except Exception as exc:
            logger.warning(
                "Higher-TF fetch failed (%s %s): %s",
                symbol,
                higher_tf,
                exc.__class__.__name__,
            )
            return None
        if not raw:
            return None
        htf_df = pd.DataFrame(
            raw, columns=["ts", "open", "high", "low", "close", "volume"]
        )
        if len(htf_df) > 1:
            htf_df = htf_df.iloc[:-1].reset_index(drop=True)
        return htf_df if not htf_df.empty else None

    def _notify(self, event_type: str, **kwargs: Any) -> None:
        if self._notifier:
            try:
                self._notifier(event_type, **kwargs)
            except Exception as exc:
                from app.monitoring.metrics import notifications_failed

                notifications_failed.labels(kind="bridge").inc()
                logger.error("Notification failed: %s", exc.__class__.__name__)


_pipeline: SignalPipeline | None = None


def get_pipeline() -> SignalPipeline:
    """Get or create the singleton SignalPipeline."""
    global _pipeline
    if _pipeline is None:
        _pipeline = SignalPipeline()
    return _pipeline
