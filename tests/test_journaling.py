import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from app.services.signal_service import SignalPipeline
from app.db.repository import StateRepository
from app.knowledge_base.embeddings import EmbeddingProvider
from app.knowledge_base.reasoning import ReasoningEngine
from app.core.enums import SignalDirection

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def pipeline():
    return SignalPipeline()

def test_journaling_pipeline_end_to_end(mock_db):
    """
    Test the full journaling flow:
    1. Ingest AI lesson (ReasoningEngine & Repository)
    2. Run a new signal cycle (SignalPipeline calls Retriever & ReasoningEngine)
    3. Verify the lesson is retrieved and used in the explanation.
    """
    repo = StateRepository(mock_db)
    embedder = EmbeddingProvider(dimension=1536)
    
    # --- PHASE 1: Ingest Lesson ---
    outcome = {
        "symbol": "BTC/USDT",
        "direction": "LONG",
        "reason": "TAKE_PROFIT"
    }
    
    lesson = "Capturing profit on BTC LONG worked well due to strong support."
    vector = embedder.embed(lesson)
    
    # Mock repository ingestion
    with patch.object(repo, 'ingest_trade_insight') as mock_ingest:
        repo.ingest_trade_insight(lesson, vector, outcome)
        mock_ingest.assert_called_once()
        passed_vector = mock_ingest.call_args[0][1]
        assert len(passed_vector) == 1536

    # --- PHASE 2: Retrieval in next cycle ---
    # Mock the DB search results
    with patch.object(StateRepository, 'search_similar_insights', return_value=[lesson]) as mock_search:
        pipeline = SignalPipeline()
        pipeline.market_data.fetch_ohlcv = MagicMock(return_value=[[1600000000000, 60000, 61000, 59000, 60500, 100]])
        
        # Mock strategy to return a new signal
        from app.schemas.signal import SignalContract
        strategy_mock = MagicMock()
        strategy_mock.generate.return_value = SignalContract(
            symbol="BTC/USDT", timeframe="15m", signal=SignalDirection.LONG,
            entry_price=60500, stop_loss=59000, take_profit=64000,
            confidence=90.0, reason="Trend continuation", timestamp=datetime.now(timezone.utc)
        )
        
        # Mock the state snapshot with a real RuntimeState object
        from app.core.state import RuntimeState

        state_snapshot = RuntimeState(
            paused=False,
            symbols=["BTC/USDT"],
            timeframes=["15m"],
            strategy="ema_rsi",
            signals=[],
            recent_outcomes=[],
        )
        with patch('app.services.signal_service.build_strategy', return_value=strategy_mock):
            with patch.object(StateRepository, 'get_runtime_state_snapshot', return_value=state_snapshot):
                # Mock record_signal
                with patch.object(StateRepository, 'record_signal', return_value=123):
                    # Mock explain to verify context injection
                    with patch.object(ReasoningEngine, 'explain', return_value="Explanation with context") as mock_explain:
                        pipeline.run_cycle(mock_db)
                        
                        # Verify search was called
                        mock_search.assert_called_once()
                        
                        # Verify explanation received the lesson!!!!
                        context_arg = mock_explain.call_args[1]["context"]
                        assert lesson in context_arg

if __name__ == "__main__":
    test_journaling_pipeline_end_to_end(MagicMock())
