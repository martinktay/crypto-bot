from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.core.enums import SignalDirection
from app.schemas.signal import SignalContract
from app.strategies.base import Strategy
from app.utils.candles import candle_close_timestamp
from app.utils.indicators import higher_timeframe_trend


class BreakoutVolumeStrategy(Strategy):
    """Range-breakout with volume confirmation and EMA200 trend filter.

    Signals fire only when the latest closed bar *crosses* the prior
    range_high/range_low while volume exceeds the moving average. The caller
    is expected to drop the in-progress bar before passing candles in.
    """

    name = "breakout_volume"

    def generate(
        self,
        symbol: str,
        timeframe: str,
        candles: pd.DataFrame,
        params: dict[str, Any] | None = None,
    ) -> SignalContract:
        data = candles.copy()
        p = params or {}
        lookback = p.get("range_period", 20)
        vol_mult = p.get("volume_multiplier", 1.0)
        tp_r = p.get("take_profit_r_multiple", 2.0)
        atr_sl_mult = p.get("atr_sl_multiple", 1.5)

        if len(data) < max(lookback + 2, 200):
            return self._hold_signal(symbol, timeframe, data, "Insufficient history")

        # Range computed *up to (but not including)* the current closed bar to
        # avoid the bar we're testing against being part of its own range.
        range_high = data["high"].iloc[:-1].rolling(lookback).max().iloc[-1]
        range_low = data["low"].iloc[:-1].rolling(lookback).min().iloc[-1]
        avg_volume = data["volume"].rolling(lookback).mean().iloc[-1] * vol_mult

        last = data.iloc[-1]
        prev = data.iloc[-2]
        price = float(last["close"])

        ema_200 = data["close"].ewm(span=200, adjust=False).mean().iloc[-1]
        is_uptrend = price > ema_200
        is_downtrend = price < ema_200

        tr = pd.concat(
            [
                data["high"] - data["low"],
                (data["high"] - data["close"].shift()).abs(),
                (data["low"] - data["close"].shift()).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr_value = float(tr.rolling(window=14).mean().iloc[-1])
        sl_distance = atr_value * atr_sl_mult if atr_value > 0 else price * 0.01

        higher_tf_candles = p.get("higher_tf_candles")
        higher_trend = higher_timeframe_trend(higher_tf_candles) if higher_tf_candles is not None else 0

        breakout_up = (
            prev["close"] <= range_high
            and price > range_high
            and last["volume"] > avg_volume
            and is_uptrend
        )
        breakout_down = (
            prev["close"] >= range_low
            and price < range_low
            and last["volume"] > avg_volume
            and is_downtrend
        )

        if breakout_up:
            if higher_trend < 0:
                return self._hold_signal(
                    symbol,
                    timeframe,
                    data,
                    "Breakout up blocked by higher-TF downtrend",
                    atr_value=atr_value,
                )
            sig = SignalDirection.LONG
            stop = price - sl_distance
            take = price + sl_distance * tp_r
            reason = "Breakout above range high with volume confirmation"
        elif breakout_down:
            if higher_trend > 0:
                return self._hold_signal(
                    symbol,
                    timeframe,
                    data,
                    "Breakdown blocked by higher-TF uptrend",
                    atr_value=atr_value,
                )
            sig = SignalDirection.SHORT
            stop = price + sl_distance
            take = price - sl_distance * tp_r
            reason = "Breakdown below range low with volume confirmation"
        else:
            return self._hold_signal(
                symbol, timeframe, data, "No breakout", atr_value=atr_value
            )

        trend_label = {1: "HTF up", -1: "HTF down", 0: "HTF n/a"}[higher_trend]
        reason = f"{reason}; {trend_label}"

        confidence = 65.0

        return SignalContract(
            symbol=symbol,
            timeframe=timeframe,
            signal=sig,
            entry_price=price,
            stop_loss=float(stop),
            take_profit=float(take),
            confidence=confidence,
            order_type="LIMIT",
            reason=reason,
            atr_value=atr_value,
            timestamp=candle_close_timestamp(last),
        )

    def _hold_signal(
        self,
        symbol: str,
        timeframe: str,
        data: pd.DataFrame,
        reason: str,
        atr_value: float | None = None,
    ) -> SignalContract:
        last = data.iloc[-1] if len(data) else None
        price = float(last["close"]) if last is not None else 0.0
        return SignalContract(
            symbol=symbol,
            timeframe=timeframe,
            signal=SignalDirection.HOLD,
            entry_price=price,
            stop_loss=price,
            take_profit=price,
            confidence=0.0,
            order_type="LIMIT",
            reason=reason,
            atr_value=atr_value,
            timestamp=candle_close_timestamp(last) if last is not None else datetime.now(timezone.utc),
        )
