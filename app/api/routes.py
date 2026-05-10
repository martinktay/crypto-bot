from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import ApiKeyDep
from app.core.enums import SignalDirection
from app.db.repository import StateRepository
from app.db.session import get_db
from app.schemas.backtest import BacktestRequest, BacktestResult
from app.schemas.signal import SignalContract
from app.optimization.backtester import BacktestService
from app.services.signal_service import get_pipeline
from app.strategies.registry import STRATEGIES

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/status")
def status(db: Session = Depends(get_db), _: None = ApiKeyDep) -> dict:
    repo = StateRepository(db)
    state = repo.get_runtime_state_snapshot()
    summary = repo.get_signal_performance_summary()

    return {
        "paused": state.paused,
        "symbols": state.symbols,
        "timeframes": state.timeframes,
        "strategy": state.strategy,
        "total_signals": summary["total_signals"],
        "signal_accuracy": summary["win_rate"],
        "avg_growth": summary["avg_growth"],
        "max_ae": summary["max_ae"],
        "recent_outcomes_count": len(state.signals),
    }


@router.get("/signals")
def signals(db: Session = Depends(get_db), _: None = ApiKeyDep) -> list[SignalContract]:
    state = StateRepository(db).get_runtime_state_snapshot()
    if not state.signals:
        return [
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
        ]
    return state.signals


@router.get("/why/{index}")
def why(index: int, db: Session = Depends(get_db), _: None = ApiKeyDep) -> dict:
    repo = StateRepository(db)
    outcomes = repo.get_recent_outcomes()
    if index < 0 or index >= len(outcomes):
        return {"result": "not_found"}
    return outcomes[index]


@router.get("/insights")
def insights(db: Session = Depends(get_db), _: None = ApiKeyDep) -> dict:
    repo = StateRepository(db)
    state = repo.get_runtime_state_snapshot()
    outcomes = repo.get_recent_outcomes()
    
    longs = len([s for s in state.signals[:50] if s.signal == SignalDirection.LONG])
    shorts = len([s for s in state.signals[:50] if s.signal == SignalDirection.SHORT])
    
    # Fetch recent 'lessons' from knowledge base
    lessons = repo.get_knowledge_documents(source_type="optimization_lesson", limit=3)
    
    return {
        "recent_signal_count": len(state.signals[:50]),
        "recent_longs": longs,
        "recent_shorts": shorts,
        "recent_outcomes": outcomes[:10],
        "recent_lessons": [
            {"title": doc.title, "content": doc.content, "metadata": doc.metadata_json}
            for doc in lessons
        ]
    }


@router.post("/signals/run")
def run_signal_cycle(db: Session = Depends(get_db), _: None = ApiKeyDep) -> dict:
    state = StateRepository(db).get_runtime_state_snapshot()
    if state.paused:
        return {"result": "paused"}
    pipeline = get_pipeline()
    outcomes = pipeline.run_cycle(db)
    return {"result": "ok", "count": len(outcomes), "outcomes": outcomes}





@router.post("/telegram/ping")
def telegram_ping(_: None = ApiKeyDep) -> dict[str, object]:
    """Deliver a benign HTML ping to TELEGRAM_GROUP_CHAT_ID / admin DM (trade-signal parity)."""
    from app.telegram_bot.service import TelegramNotifier

    notifier = TelegramNotifier()
    pings = notifier.ping_destinations()
    if not notifier.enabled:
        return {
            "ok": False,
            "telegram_configured": False,
            "detail": "missing token or chat id",
            "pings": [],
        }
    if not pings:
        return {
            "ok": False,
            "telegram_configured": True,
            "detail": "no broadcast destinations",
            "pings": [],
        }
    all_ok = all(bool(p.get("ok")) for p in pings)
    return {
        "ok": all_ok,
        "telegram_configured": True,
        "pings": pings,
    }


@router.post("/symbols")
def set_symbols(payload: list[str], db: Session = Depends(get_db), _: None = ApiKeyDep) -> dict[str, list[str]]:
    StateRepository(db).update_symbols_timeframes_strategy(symbols=payload)
    return {"symbols": payload}


@router.post("/strategy/config")
def set_strategy(payload: dict, db: Session = Depends(get_db), _: None = ApiKeyDep) -> dict:
    strategy_name = payload.get("name", "ema_rsi")
    if strategy_name not in STRATEGIES:
        return {"result": "rejected", "supported": list(STRATEGIES)}
    StateRepository(db).update_symbols_timeframes_strategy(strategy=strategy_name)
    return {"strategy": strategy_name}


@router.post("/pause")
def pause(db: Session = Depends(get_db), _: None = ApiKeyDep) -> dict[str, bool]:
    StateRepository(db).update_mode(paused=True)
    return {"paused": True}


@router.post("/resume")
def resume(db: Session = Depends(get_db), _: None = ApiKeyDep) -> dict[str, bool]:
    StateRepository(db).update_mode(paused=False)
    return {"paused": False}


@router.post("/backtest", response_model=BacktestResult)
def run_backtest(request: BacktestRequest, db: Session = Depends(get_db), _: None = ApiKeyDep) -> BacktestResult:
    service = BacktestService()
    repo = StateRepository(db)
    return service.run_backtest(request, repo=repo)


@router.get("/backtest/history")
def get_backtest_history(limit: int = 10, db: Session = Depends(get_db), _: None = ApiKeyDep) -> list:
    repo = StateRepository(db)
    return repo.get_backtest_history(limit=limit)


@router.post("/optimize")
async def run_optimization(db: Session = Depends(get_db), _: None = ApiKeyDep):
    from app.services.optimizer import OptimizerEngine
    from app.schemas.optimizer import OptimizerRequest
    from app.api.ws_routes import broadcast_signal
    from app.knowledge_base.reasoning import ReasoningEngine
    from app.knowledge_base.embeddings import EmbeddingProvider
    
    repo = StateRepository(db)
    engine = OptimizerEngine()
    
    # Using fixed request for UI triggers, could be parameterized later
    request = OptimizerRequest(population_size=10, generations=2) 
    
    logger.info("Triggering hybrid optimization sequence...")
    result = await engine.run(request)
    
    # --- PHASE 7: Closed-Loop Learning (Semantic Archiving) ---
    try:
        reasoner = ReasoningEngine()
        embedder = EmbeddingProvider()
        
        # Analyze why these params worked
        lesson_text = reasoner.analyze_simulation_result(result)
        vector = embedder.embed(lesson_text)
        
        repo.ingest_knowledge_document(
            title=f"Evolution Lesson: {result.strategy} {result.symbol}",
            content=lesson_text,
            source_type="optimization_lesson",
            vector=vector,
            metadata={"strategy": result.strategy, "symbol": result.symbol, "sharpe": result.best_sharpe}
        )
        logger.info("Neural lesson archived: %s", result.strategy)
    except Exception as exc:
        logger.error("Failed to archive neural lesson: %s", exc)

    # Broadcast full result to connected browsers
    await broadcast_signal("optimization_complete", result.model_dump(mode="json"))
    
    return result


@router.post("/scanner/run")
async def run_scanner(db: Session = Depends(get_db), _: None = ApiKeyDep):
    """Run a global Alpha Scan for futures trading opportunities."""
    from app.services.scanner import FuturesScanner
    
    scanner = FuturesScanner()
    # Scaning top 50, but only returning top 10 results
    results = await scanner.scan(limit=50)
    
    return {
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "candidates": results[:10]
    }
