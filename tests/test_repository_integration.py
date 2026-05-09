"""Integration tests for StateRepository against a real (SQLite) database."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.enums import SignalDirection
from app.db.repository import StateRepository
from app.models.entities import Signal
from tests.conftest import make_bot_setting, make_signal_contract


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def test_get_or_create_settings_idempotent(db_session) -> None:
    """Calling get_or_create_settings twice returns the same row."""
    repo = StateRepository(db_session)
    s1 = repo.get_or_create_settings()
    s2 = repo.get_or_create_settings()
    assert s1.id == s2.id


def test_get_or_create_settings_defaults(db_session) -> None:
    """First call inserts defaults from config."""
    repo = StateRepository(db_session)
    s = repo.get_or_create_settings()
    assert s.paused is False
    assert s.execution_mode == "signal_only"


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

def test_record_signal_persists(db_session) -> None:
    """A recorded signal appears in the runtime state snapshot."""
    make_bot_setting(db_session)
    repo = StateRepository(db_session)
    sig = make_signal_contract()
    sig_id = repo.record_signal(sig, ai_explanation="test explanation")
    assert sig_id > 0

    state = repo.get_runtime_state_snapshot()
    assert len(state.signals) == 1
    assert state.signals[0].symbol == "BTC/USDT"


# ---------------------------------------------------------------------------
# Mode & Config Updates
# ---------------------------------------------------------------------------

def test_update_mode_persists(db_session) -> None:
    """Changing execution mode is reflected in the next snapshot."""
    make_bot_setting(db_session)
    repo = StateRepository(db_session)
    repo.update_mode(paused=True)

    state = repo.get_runtime_state_snapshot()
    assert state.paused is True


def test_update_symbols_and_strategy(db_session) -> None:
    """Switching symbols and strategy is reflected in snapshot."""
    make_bot_setting(db_session)
    repo = StateRepository(db_session)
    repo.update_symbols_timeframes_strategy(
        symbols=["ETH/USDT", "SOL/USDT"], strategy="breakout_volume"
    )

    state = repo.get_runtime_state_snapshot()
    assert state.symbols == ["ETH/USDT", "SOL/USDT"]
    assert state.strategy == "breakout_volume"


