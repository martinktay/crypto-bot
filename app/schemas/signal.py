from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import SignalDirection


class SignalContract(BaseModel):
    symbol: str
    timeframe: str
    signal: SignalDirection
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float = Field(ge=0.0, le=100.0)
    order_type: str = "LIMIT"
    reason: str
    ai_explanation: str = ""
    atr_value: float | None = None
    # Exchange the OHLCV used to compute this signal came from. Stored on
    # the row so OutcomeTracker re-fetches against the same exchange and
    # the broadcast can label the source.
    exchange_id: str = "binance"
    timestamp: datetime
