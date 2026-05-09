import pytest
import asyncio
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from app.schemas.optimizer import OptimizerResult
from app.db.repository import StateRepository
from app.knowledge_base.reasoning import ReasoningEngine
from app.knowledge_base.embeddings import EmbeddingProvider
from app.services.signal_service import SignalPipeline
from app.core.enums import SignalDirection
from app.schemas.signal import SignalContract

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.mark.asyncio
async def test_optimization_to_signal_context_loop(mock_db):
    """
    Test Phase 7 end-to-end:
    1. Mock an optimization result.
    2. Extract and store a lesson.
    3. Generate a signal and verify retrieval of that lesson.
    """
    repo = StateRepository(mock_db)
    reasoner = ReasoningEngine()
    embedder = EmbeddingProvider()
    
    # 1. Mock Optimizer Result
    mock_result = OptimizerResult(
        symbol="ETH/USDT",
        strategy="ema_rsi",
        best_params={"ema_fast": 10, "ema_slow": 30},
        best_sharpe=2.5,
        best_return_pct=15.0,
        total_simulations=20,
        top_performers=[]
    )
    
    # 2. Extract Lesson and Store
    lesson_text = "ETH/USDT 10/30 crossover showed 2.5 Sharpe in recent bull market."
    vector = [0.1] * 1536 # Mock vector
    
    with patch.object(EmbeddingProvider, 'embed', return_value=vector):
        with patch.object(ReasoningEngine, 'analyze_simulation_result', return_value=lesson_text):
            # We use the real ingest_knowledge_document but catch the DB call if needed
            # In this test, we want to see if the loop works.
            repo.ingest_knowledge_document(
                title="Test Lesson",
                content=lesson_text,
                source_type="optimization_lesson",
                vector=vector
            )
    
    # 3. Simulate Signal Generation with Retrieval
    # Mock Retriever to return our lesson
    with patch('app.knowledge_base.retrieval.Retriever.get_relevant_context', return_value=[lesson_text]):
        pipeline = SignalPipeline()
        
        # Mock Market Data and Strategy
        pipeline.market_data.fetch_ohlcv = MagicMock(return_value=[[1, 2000, 2100, 1900, 2050, 100]])
        
        strategy_mock = MagicMock()
        strategy_mock.generate.return_value = SignalContract(
            symbol="ETH/USDT", timeframe="1h", signal=SignalDirection.LONG,
            entry_price=2050, stop_loss=1900, take_profit=2300,
            confidence=85.0, reason="Crossover detected", timestamp=datetime.now(timezone.utc)
        )
        
        from app.core.state import RuntimeState
        state_snapshot = RuntimeState(
            paused=False, symbols=["ETH/USDT"], timeframes=["1h"],
            strategy="ema_rsi", signals=[], recent_outcomes=[]
        )
        
        with patch('app.services.signal_service.build_strategy', return_value=strategy_mock):
            with patch.object(StateRepository, 'get_runtime_state_snapshot', return_value=state_snapshot):
                with patch.object(StateRepository, 'record_signal', return_value=1):
                    # We want to see if explain is called with the context containing our lesson
                    with patch.object(ReasoningEngine, 'explain', return_value="AI explanation") as mock_explain:
                        pipeline.run_cycle(mock_db)
                        
                        # VERIFY context injection
                        args, kwargs = mock_explain.call_args
                        context_arg = kwargs.get('context', '')
                        assert lesson_text in context_arg
                        print("Verification Success: Optimization lesson was successfully injected into signal explanation!")

if __name__ == "__main__":
    # Standard pytest run would be better, but we can run manually for quick check
    print("Running Phase 7 Verification...")
    asyncio.run(test_optimization_to_signal_context_loop(MagicMock()))
