"""API endpoint tests using FastAPI TestClient with SQLite DB."""

from __future__ import annotations

import pytest

from tests.conftest import make_bot_setting


class TestHealthAndStatus:
    def test_health_returns_ok(self, test_client) -> None:
        resp = test_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "timestamp" in data

    def test_status_returns_defaults(self, test_client, db_session) -> None:
        make_bot_setting(db_session)
        resp = test_client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["paused"] is False
        assert "paper_balance" not in data


class TestSignalsEndpoint:
    def test_signals_empty_returns_hold(self, test_client, db_session) -> None:
        make_bot_setting(db_session)
        resp = test_client.get("/signals")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["signal"] == "HOLD"


class TestPauseResume:
    def test_pause_and_resume(self, test_client, db_session) -> None:
        make_bot_setting(db_session)

        resp = test_client.post("/pause")
        assert resp.status_code == 200
        assert resp.json()["paused"] is True

        resp = test_client.post("/resume")
        assert resp.status_code == 200
        assert resp.json()["paused"] is False

        # Verify via status
        resp = test_client.get("/status")
        assert resp.json()["paused"] is False


class TestSymbolsEndpoint:
    def test_set_symbols(self, test_client, db_session) -> None:
        make_bot_setting(db_session)
        resp = test_client.post("/symbols", json=["ETH/USDT", "SOL/USDT"])
        assert resp.status_code == 200
        assert resp.json()["symbols"] == ["ETH/USDT", "SOL/USDT"]


class TestStrategyEndpoint:
    def test_set_strategy_valid(self, test_client, db_session) -> None:
        make_bot_setting(db_session)
        resp = test_client.post("/strategy/config", json={"name": "ema_rsi"})
        assert resp.status_code == 200
        assert resp.json()["strategy"] == "ema_rsi"

    def test_set_strategy_invalid_rejected(self, test_client, db_session) -> None:
        make_bot_setting(db_session)
        resp = test_client.post("/strategy/config", json={"name": "nonexistent_strat"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"] == "rejected"
        assert "supported" in data


class TestWhyEndpoint:
    def test_why_not_found(self, test_client, db_session) -> None:
        make_bot_setting(db_session)
        resp = test_client.get("/why/9999")
        assert resp.status_code == 200
        assert resp.json()["result"] == "not_found"


class TestApprovalsEndpoint:
    def test_approvals_empty(self, test_client, db_session) -> None:
        make_bot_setting(db_session)
        resp = test_client.get("/approvals")
        assert resp.status_code == 200
        assert resp.json() == []
