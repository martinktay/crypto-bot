from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.core.enums import SignalDirection
from app.schemas.signal import SignalContract
from app.services.signal_service import SignalPipeline


@patch("app.services.signal_service.StateRepository")
@patch("app.services.signal_service.Retriever")
@patch("app.services.signal_service.build_strategy")
def test_pipeline_fetches_similar_insights(mock_build, mock_retriever_cls, mock_repo_cls) -> None:
    pipeline = SignalPipeline()
    
    # Mock Market
    pipeline.market_data = MagicMock()
    pipeline.market_data.fetch_ohlcv.return_value = [[1, 2, 3, 4, 5, 6]]
    # The pipeline now resolves symbols through the provider's registry-aware
    # parse() so unknown exchange prefixes don't desync from where the data
    # actually came from. The test universe is unprefixed, so parse always
    # returns the default exchange.
    pipeline.market_data.parse.return_value = ("binance", "BTC/USDT")
    
    # Mock Strategy
    strategy_mock = MagicMock()
    strategy_mock.generate.return_value = SignalContract(
        symbol="BTC/USDT", timeframe="15m", signal=SignalDirection.LONG, 
        entry_price=10, stop_loss=9, take_profit=12, confidence=80, reason="test",
        timestamp=datetime.now(timezone.utc)
    )
    mock_build.return_value = strategy_mock

    retriever_mock = MagicMock()
    retriever_mock.get_relevant_context.return_value = ["Lesson 1", "Lesson 2"]
    mock_retriever_cls.return_value = retriever_mock

    # Mock DB
    repo_mock = MagicMock()
    # State Mock
    state_mock = MagicMock()
    state_mock.paused = False
    state_mock.symbols = ["BTC/USDT"]
    state_mock.timeframes = ["15m"]
    state_mock.signals = []
    state_mock.strategy = "ema_rsi"
    
    repo_mock.get_runtime_state_snapshot.return_value = state_mock
    mock_repo_cls.return_value = repo_mock

    # Mock AI Reader
    pipeline.embedder = MagicMock()
    pipeline.embedder.embed.return_value = [0.5] * 1536
    
    pipeline.reasoning_engine = MagicMock()
    pipeline.reasoning_engine.explain.return_value = "Explained."
    
    # Silence notifier
    pipeline.set_notifier(MagicMock())

    pipeline.run_cycle(MagicMock())

    # Assert search was done!
    retriever_mock.get_relevant_context.assert_called_once()
    
    # Assert explanation received the context String!
    pipeline.reasoning_engine.explain.assert_called_once()
    call_args = pipeline.reasoning_engine.explain.call_args[1]
    assert "Past applicable lessons & strategy insights:" in call_args["context"]
    assert "Lesson 1" in call_args["context"]
