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
    reason: str
    timestamp: datetime
