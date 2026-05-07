"""Seed the knowledge base with default strategy documents."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

SEED_DOCUMENTS = [
    {
        "source_type": "strategy_doc",
        "title": "EMA Crossover + RSI Strategy",
        "content": (
            "The EMA crossover with RSI filter strategy generates signals based on "
            "the relationship between fast and slow Exponential Moving Averages, "
            "confirmed by the Relative Strength Index.\n\n"
            "LONG signal: Fast EMA crosses above slow EMA and RSI is below the "
            "overbought threshold (default 70). This indicates bullish momentum "
            "that is not yet overextended.\n\n"
            "SHORT signal: Fast EMA crosses below slow EMA and RSI is above the "
            "oversold threshold (default 30). This indicates bearish momentum "
            "that is not yet oversold.\n\n"
            "HOLD: When conditions do not clearly align for either direction.\n\n"
            "Default parameters: EMA_FAST=12, EMA_SLOW=26, RSI_PERIOD=14. "
            "Stop loss is placed at STOP_LOSS_BUFFER_PERCENT from entry. "
            "Take profit is TAKE_PROFIT_R_MULTIPLE times the stop distance.\n\n"
            "Best used on 15m timeframe for BTC/USDT. Higher timeframes "
            "produce fewer but potentially more reliable signals."
        ),
        "metadata_json": {"version": "1.0", "pair": "BTC/USDT", "timeframe": "15m"},
    },
    {
        "source_type": "strategy_doc",
        "title": "Risk Management Rules",
        "content": (
            "Risk rules are enforced before every trade execution:\n\n"
            "1. Risk-reward ratio must meet MIN_RISK_REWARD_RATIO (default 1.2).\n"
            "2. Maximum open positions limited by MAX_OPEN_POSITIONS (default 3).\n"
            "3. Signal cooldown of SIGNAL_COOLDOWN_MINUTES between same-direction "
            "signals on the same pair.\n"
            "4. Daily loss cap at MAX_DAILY_LOSS_PERCENT of starting balance.\n"
            "5. Position size based on RISK_PER_TRADE fraction of account balance.\n\n"
            "These rules cannot be overridden by AI reasoning or signal confidence."
        ),
        "metadata_json": {"version": "1.0", "category": "risk"},
    },
]


def seed_knowledge_base_if_empty() -> None:
    """Insert seed documents if the knowledge_documents table is empty.

    Requires a running PostgreSQL connection. Logs and skips gracefully on failure.
    """
    try:
        from sqlalchemy import func, select

        from app.db.session import SessionLocal
        from app.models.entities import KnowledgeDocument

        db = SessionLocal()
        try:
            count = db.execute(select(func.count()).select_from(KnowledgeDocument)).scalar()
            if count and count > 0:
                logger.info("Knowledge base has %d documents, skipping seed", count)
                return

            for doc_data in SEED_DOCUMENTS:
                doc = KnowledgeDocument(
                    source_type=doc_data["source_type"],
                    title=doc_data["title"],
                    content=doc_data["content"],
                    metadata_json=doc_data["metadata_json"],
                    created_at=datetime.now(timezone.utc),
                )
                db.add(doc)

            db.commit()
            logger.info("Seeded %d knowledge base documents", len(SEED_DOCUMENTS))
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Knowledge base seeding skipped (DB unavailable): %s", exc)
