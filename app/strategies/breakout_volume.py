from datetime import datetime, timezone

import pandas as pd

from app.core.enums import SignalDirection
from app.schemas.signal import SignalContract
from app.strategies.base import Strategy


class BreakoutVolumeStrategy(Strategy):
    name = "breakout_volume"

    def generate(self, symbol: str, timeframe: str, candles: pd.DataFrame) -> SignalContract:
        data = candles.copy()
        range_high = data["high"].rolling(20).max().iloc[-2]
        range_low = data["low"].rolling(20).min().iloc[-2]
        avg_volume = data["volume"].rolling(20).mean().iloc[-1]
        last = data.iloc[-1]
        price = float(last["close"])

        if price > range_high and last["volume"] > avg_volume:
            sig = SignalDirection.LONG
            stop = range_high * 0.995
            take = price * 1.025
        elif price < range_low and last["volume"] > avg_volume:
            sig = SignalDirection.SHORT
            stop = range_low * 1.005
            take = price * 0.975
        else:
            sig = SignalDirection.HOLD
            stop = price
            take = price

        confidence = 65.0 if sig != SignalDirection.HOLD else 40.0
        return SignalContract(
            symbol=symbol,
            timeframe=timeframe,
            signal=sig,
            entry_price=price,
            stop_loss=float(stop),
            take_profit=float(take),
            confidence=confidence,
            reason="20-period breakout with volume confirmation",
            timestamp=datetime.now(timezone.utc),
        )
