"""HTTP API routes for operating the MVP signal bot."""

from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.enums import SignalDirection, TradingMode
from app.core.state import get_runtime_state
from app.schemas.mode import ModeUpdateRequest
from app.schemas.signal import SignalContract
from app.services.signal_service import SignalPipeline

MVP_STRATEGIES = {"ema_rsi"}

router = APIRouter()
pipeline = SignalPipeline()


class ApprovalDecision(BaseModel):
    approved: bool


def _require_admin_token(x_admin_token: str | None) -> None:
    if settings.admin_api_token and x_admin_token != settings.admin_api_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/status")
def status() -> dict:
    state = get_runtime_state()
    return {
        "mode": state.mode,
        "paused": state.paused,
        "live_enabled": settings.enable_live_trading,
        "symbols": state.symbols,
        "timeframes": state.timeframes,
        "strategy": state.strategy,
        "pending_approvals": len(state.approvals),
        "recent_outcomes": len(state.recent_outcomes),
    }


@router.get("/signals")
def signals() -> list[SignalContract]:
    state = get_runtime_state()
    if not state.signals:
        state.signals.append(
            SignalContract(
                symbol="BTC/USDT",
                timeframe="15m",
                signal=SignalDirection.HOLD,
                entry_price=0,
                stop_loss=0,
                take_profit=0,
                confidence=0,
                reason="No signal generated yet",
                timestamp=datetime.now(timezone.utc),
            )
        )
    return state.signals


@router.get("/why/{index}")
def why(index: int) -> dict:
    state = get_runtime_state()
    if index < 0 or index >= len(state.recent_outcomes):
        return {"result": "not_found"}
    return state.recent_outcomes[index]


@router.get("/insights")
def insights() -> dict:
    state = get_runtime_state()
    longs = len([s for s in state.signals[:50] if s.signal == SignalDirection.LONG])
    shorts = len([s for s in state.signals[:50] if s.signal == SignalDirection.SHORT])
    return {
        "recent_signal_count": len(state.signals[:50]),
        "recent_longs": longs,
        "recent_shorts": shorts,
        "recent_outcomes": state.recent_outcomes[:10],
    }


@router.post("/signals/run")
def run_signal_cycle(x_admin_token: str | None = Header(default=None)) -> dict:
    """Trigger one immediate signal cycle and return outcomes."""
    _require_admin_token(x_admin_token)
    state = get_runtime_state()
    if state.paused:
        return {"result": "paused"}
    outcomes = pipeline.run_cycle(state)
    return {"result": "ok", "count": len(outcomes), "outcomes": outcomes}


@router.get("/trades")
def trades() -> list:
    return get_runtime_state().trades


@router.get("/positions")
def positions() -> list:
    return get_runtime_state().positions


@router.post("/mode")
def set_mode(payload: ModeUpdateRequest, x_admin_token: str | None = Header(default=None)) -> dict[str, str]:
    _require_admin_token(x_admin_token)
    if payload.mode == TradingMode.AUTO_TRADE_LIVE:
        return {"result": "rejected: live mode disabled for MVP"}
    state = get_runtime_state()
    state.mode = payload.mode
    return {"result": f"mode set to {payload.mode.value}"}


@router.post("/symbols")
def set_symbols(payload: list[str], x_admin_token: str | None = Header(default=None)) -> dict[str, list[str]]:
    _require_admin_token(x_admin_token)
    state = get_runtime_state()
    state.symbols = payload
    return {"symbols": payload}


@router.post("/strategy/config")
def set_strategy(payload: dict, x_admin_token: str | None = Header(default=None)) -> dict:
    _require_admin_token(x_admin_token)
    strategy_name = payload.get("name", "ema_rsi")
    if strategy_name not in MVP_STRATEGIES:
        return {"result": "rejected", "supported": sorted(MVP_STRATEGIES)}
    state = get_runtime_state()
    state.strategy = strategy_name
    return {"strategy": state.strategy}


@router.get("/approvals")
def list_approvals() -> list[dict]:
    return [
        {
            "approval_id": item.approval_id,
            "symbol": item.signal.symbol,
            "signal": item.signal.signal,
            "status": item.status,
            "expires_at": item.expires_at.isoformat(),
        }
        for item in get_runtime_state().approvals.values()
    ]


@router.post("/approvals/{approval_id}")
def decide_approval(
    approval_id: str,
    payload: ApprovalDecision,
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Approve or reject a pending manual-approval signal."""
    _require_admin_token(x_admin_token)
    state = get_runtime_state()
    return pipeline.apply_approval_decision(state, approval_id, payload.approved)


@router.post("/pause")
def pause(x_admin_token: str | None = Header(default=None)) -> dict[str, bool]:
    _require_admin_token(x_admin_token)
    state = get_runtime_state()
    state.paused = True
    return {"paused": state.paused}


@router.post("/resume")
def resume(x_admin_token: str | None = Header(default=None)) -> dict[str, bool]:
    _require_admin_token(x_admin_token)
    state = get_runtime_state()
    state.paused = False
    return {"paused": state.paused}
