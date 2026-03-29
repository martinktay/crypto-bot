from datetime import datetime, timezone

import pandas as pd

from app.core.enums import SignalDirection
from app.schemas.signal import SignalContract
from app.strategies.base import Strategy


class EmaRsiStrategy(Strategy):
    name = "ema_rsi"

    def generate(self, symbol: str, timeframe: str, candles: pd.DataFrame) -> SignalContract:
        data = candles.copy()
        data["ema_fast"] = data["close"].ewm(span=12).mean()
        data["ema_slow"] = data["close"].ewm(span=26).mean()
        delta = data["close"].diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
        loss = -delta.where(delta < 0, 0.0).rolling(window=14).mean()
        rs = gain / loss.replace(0, 1e-9)
        data["rsi"] = 100 - (100 / (1 + rs))

        last = data.iloc[-1]
        price = float(last["close"])

        if last["ema_fast"] > last["ema_slow"] and last["rsi"] < 70:
            direction = SignalDirection.LONG
            stop = price * 0.99
            take = price * 1.02
        elif last["ema_fast"] < last["ema_slow"] and last["rsi"] > 30:
            direction = SignalDirection.SHORT
            stop = price * 1.01
            take = price * 0.98
        else:
            direction = SignalDirection.HOLD
            stop = price
            take = price

        confidence = float(min(95.0, max(35.0, abs(last["ema_fast"] - last["ema_slow"]) / price * 10000)))
        reason = f"EMA12/EMA26 alignment with RSI={last['rsi']:.2f}"

        return SignalContract(
            symbol=symbol,
            timeframe=timeframe,
            signal=direction,
            entry_price=price,
            stop_loss=float(stop),
            take_profit=float(take),
            confidence=confidence,
            reason=reason,
            timestamp=datetime.now(timezone.utc),
        )
