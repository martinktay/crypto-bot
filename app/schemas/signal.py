from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.core.enums import SignalDirection


class SignalContract(BaseModel):
    symbol: str
    timeframe: str
    signal: SignalDirection
    entry_price: float
    stop_loss: float
    take_profit: float
    #: Blended RSI + EMA-separation score (``ema_rsi``). Other strategies set
    #: this to their single internal strength value.
    quality_score: float = Field(default=0.0, ge=0.0, le=100.0)
    #: Legacy audit metric for ``ema_rsi`` only: $|EMA_{fast}-EMA_{slow}|/price$
    #: in bps, clamped to 40–95. ``None`` for HOLD or non–ema_rsi strategies.
    confidence_audit_ema_bps: float | None = Field(default=None)
    #: Mirrors ``quality_score`` for backward compatibility with older API/clients.
    confidence: float = Field(ge=0.0, le=100.0, default=0.0)
    order_type: str = "LIMIT"
    reason: str
    ai_explanation: str = ""
    atr_value: float | None = None
    # Exchange the OHLCV used to compute this signal came from. Stored on
    # the row so OutcomeTracker re-fetches against the same exchange and
    # the broadcast can label the source.
    exchange_id: str = "binance"
    timestamp: datetime

    @model_validator(mode="after")
    def _align_quality_and_confidence(self) -> Self:
        if self.signal == SignalDirection.HOLD:
            object.__setattr__(self, "quality_score", 0.0)
            object.__setattr__(self, "confidence", 0.0)
            object.__setattr__(self, "confidence_audit_ema_bps", None)
            return self
        if self.quality_score == 0.0 and self.confidence != 0.0:
            object.__setattr__(self, "quality_score", self.confidence)
        elif self.confidence != self.quality_score:
            object.__setattr__(self, "confidence", self.quality_score)
        elif self.quality_score != 0.0 and self.confidence == 0.0:
            object.__setattr__(self, "confidence", self.quality_score)
        return self
