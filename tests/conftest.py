"""Shared test fixtures — in-process SQLite database, TestClient, factories."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, Text
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

# --- Override settings BEFORE any app imports --------------------------------
# This prevents app.core.config from trying to read a real .env or connect to
# a real Postgres database during test collection.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "")
os.environ.setdefault("TELEGRAM_ADMIN_CHAT_ID", "")
os.environ.setdefault("TELEGRAM_GROUP_CHAT_ID", "")
os.environ.setdefault("OPENAI_API_KEY", "")

from app.core.enums import ApprovalMode, SignalDirection  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.entities import (  # noqa: E402
    BotSetting,
    KnowledgeDocument,
    KnowledgeEmbedding,
    PendingApproval,
    Signal,
)
from app.schemas.signal import SignalContract  # noqa: E402


# ---------------------------------------------------------------------------
# SQLite compatibility shim for pgvector's Vector(1536) column type.
# ---------------------------------------------------------------------------
# SQLite has no pgvector extension. We intercept DDL and swap the Vector
# column for a plain Text column so CREATE TABLE succeeds.  The actual
# vector-distance queries are skipped in integration tests (those paths
# are already covered by the mocked unit tests in test_knowledge_engine.py).
# ---------------------------------------------------------------------------

@event.listens_for(Base.metadata, "column_reflect")
def _reflect_column(inspector, table, column_info):
    """Not used directly, but keeps the listener in scope."""


def _patch_vector_column_for_sqlite(engine):
    """Replace Vector(1536) columns with Text for SQLite compatibility."""
    if "sqlite" not in str(engine.url):
        return

    for table in Base.metadata.tables.values():
        for col in table.columns:
            # pgvector columns expose a type with impl attribute
            col_type_name = type(col.type).__name__
            if col_type_name == "Vector":
                col.type = Text()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_engine():
    """Create an in-memory SQLite engine with all tables."""
    engine = create_engine(
        "sqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _patch_vector_column_for_sqlite(engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """Yield a SQLAlchemy session; rolls back after each test."""
    TestSession = sessionmaker(bind=db_engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def test_client(db_session):
    """FastAPI TestClient with the DB dependency overridden to use SQLite."""
    from fastapi.testclient import TestClient

    from app.api.routes import router
    from app.db.session import get_db

    # Create a minimal app just for testing routes (avoids lifespan side-effects
    # like Telegram polling, scheduler startup, and knowledge base seeding).
    from fastapi import FastAPI

    test_app = FastAPI()
    test_app.include_router(router)

    def _override_db():
        try:
            yield db_session
        finally:
            pass

    test_app.dependency_overrides[get_db] = _override_db

    with TestClient(test_app) as client:
        yield client


@pytest.fixture()
def seeded_db(db_session):
    """Pre-populate the DB with a BotSetting and a Signal."""
    setting = BotSetting(
        execution_mode="signal_only",
        approval_mode=ApprovalMode.MANUAL_APPROVAL,
        paused=False,
        symbols=["BTC/USDT"],
        timeframes=["15m"],
        strategy="ema_rsi",
    )
    db_session.add(setting)
    db_session.flush()

    sig = Signal(
        symbol="BTC/USDT",
        timeframe="15m",
        signal=SignalDirection.LONG,
        entry_price=60000.0,
        stop_loss=58000.0,
        take_profit=64000.0,
        confidence=80.0,
        reason="EMA crossover bullish",
        ai_explanation="Test explanation",
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db_session.add(sig)
    db_session.commit()

    return {"setting": setting, "signal": sig}


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def make_signal_contract(**overrides) -> SignalContract:
    """Build a SignalContract with sensible defaults."""
    defaults = dict(
        symbol="BTC/USDT",
        timeframe="15m",
        signal=SignalDirection.LONG,
        entry_price=60000.0,
        stop_loss=58000.0,
        take_profit=64000.0,
        confidence=80.0,
        reason="test signal",
        timestamp=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return SignalContract(**defaults)


def make_bot_setting(db: Session, **overrides) -> BotSetting:
    """Insert and return a BotSetting row."""
    defaults = dict(
        execution_mode="signal_only",
        approval_mode=ApprovalMode.AUTO,
        paused=False,
        symbols=["BTC/USDT"],
        timeframes=["15m"],
        strategy="ema_rsi",
    )
    defaults.update(overrides)
    setting = BotSetting(**defaults)
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting
