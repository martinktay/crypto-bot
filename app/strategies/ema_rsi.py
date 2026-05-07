from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.core.config import settings
from app.core.enums import SignalDirection
from app.schemas.signal import SignalContract
from app.strategies.base import Strategy
from app.utils.candles import candle_close_timestamp
from app.utils.indicators import higher_timeframe_trend


class EmaRsiStrategy(Strategy):
    """EMA crossover with RSI momentum filter.

    A signal fires only on the bar where EMA fast actually *crosses* EMA slow
    (event-based, not regime-based). Stops are derived from ATR so the risk
    engine's volatility check is mutually consistent with the SL placement.

    The caller is expected to pass only *closed* candles (drop the
    in-progress last bar) so signals reflect realized data.
    """

    name = "ema_rsi"

    def generate(
        self,
        symbol: str,
        timeframe: str,
        candles: pd.DataFrame,
        params: dict[str, Any] | None = None,
    ) -> SignalContract:
        data = candles.copy()
        p = params or {}

        ema_fast_n = p.get("ema_fast", settings.ema_fast)
        ema_slow_n = p.get("ema_slow", settings.ema_slow)
        rsi_period = p.get("rsi_period", settings.rsi_period)
        rsi_long_threshold = p.get("rsi_long_threshold", settings.rsi_long_threshold)
        rsi_short_threshold = p.get("rsi_short_threshold", settings.rsi_short_threshold)
        tp_mult = p.get("take_profit_r_multiple", settings.take_profit_r_multiple)
        atr_sl_mult = p.get("atr_sl_multiple", 2.0)

        # ATR(14) — used both as risk reference and for SL placement.
        tr = pd.concat(
            [
                data["high"] - data["low"],
                (data["high"] - data["close"].shift()).abs(),
                (data["low"] - data["close"].shift()).abs(),
            ],
            axis=1,
        ).max(axis=1)
        data["atr"] = tr.rolling(window=14).mean()

        # Indicators (adjust=False matches TA-Lib / TradingView semantics).
        data["ema_fast"] = data["close"].ewm(span=ema_fast_n, adjust=False).mean()
        data["ema_slow"] = data["close"].ewm(span=ema_slow_n, adjust=False).mean()

        delta = data["close"].diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=rsi_period).mean()
        loss = -delta.where(delta < 0, 0.0).rolling(window=rsi_period).mean()
        rs = gain / loss.replace(0, 1e-9)
        data["rsi"] = 100 - (100 / (1 + rs))

        if len(data) < 2:
            return self._hold_signal(symbol, timeframe, data, "Insufficient data")

        last = data.iloc[-1]
        prev = data.iloc[-2]
        price = float(last["close"])
        atr_value = float(last["atr"]) if pd.notna(last["atr"]) else 0.0

        rsi_value = float(last["rsi"]) if pd.notna(last["rsi"]) else 50.0
        # LONG  needs bullish momentum (RSI > 50) and not overbought (< rsi_long_threshold)
        # SHORT needs bearish momentum (RSI < 50) and not oversold (> rsi_short_threshold)
        bullish_momentum = 50 < rsi_value < rsi_long_threshold
        bearish_momentum = rsi_short_threshold < rsi_value < 50

        cross_up = (
            prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]
        )
        cross_down = (
            prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]
        )

        # SL is ATR-derived; if ATR is zero (synthetic data), fall back to a
        # small percentage so the strategy still produces a usable contract.
        sl_distance = atr_value * atr_sl_mult if atr_value > 0 else price * 0.01

        # Higher-timeframe trend filter (EMA200 on the higher TF).
        # +1=up, -1=down, 0=unknown/disabled. LONG requires non-bearish trend,
        # SHORT requires non-bullish trend.
        higher_tf_candles = (p.get("higher_tf_candles") if isinstance(p, dict) else None)
        higher_trend = higher_timeframe_trend(higher_tf_candles) if higher_tf_candles is not None else 0

        if cross_up and bullish_momentum:
            if higher_trend < 0:
                return self._hold_signal(
                    symbol,
                    timeframe,
                    data,
                    f"LONG cross blocked by higher-TF downtrend (rsi={rsi_value:.1f})",
                    atr_value=atr_value,
                )
            direction = SignalDirection.LONG
            stop = price - sl_distance
            take = price + sl_distance * tp_mult
        elif cross_down and bearish_momentum:
            if higher_trend > 0:
                return self._hold_signal(
                    symbol,
                    timeframe,
                    data,
                    f"SHORT cross blocked by higher-TF uptrend (rsi={rsi_value:.1f})",
                    atr_value=atr_value,
                )
            direction = SignalDirection.SHORT
            stop = price + sl_distance
            take = price - sl_distance * tp_mult
        else:
            return self._hold_signal(
                symbol,
                timeframe,
                data,
                f"No crossover (rsi={rsi_value:.1f})",
                atr_value=atr_value,
            )

        # Confidence: scaled separation between EMAs vs price, soft-capped.
        ema_sep_bps = abs(last["ema_fast"] - last["ema_slow"]) / max(price, 1e-9) * 10000
        confidence = float(min(95.0, max(40.0, ema_sep_bps)))

        trend_label = {1: "HTF up", -1: "HTF down", 0: "HTF n/a"}[higher_trend]
        reason = (
            f"EMA{ema_fast_n}/EMA{ema_slow_n} cross "
            f"({'up' if direction == SignalDirection.LONG else 'down'}) "
            f"with RSI({rsi_period})={rsi_value:.1f}, ATR={atr_value:.2f}, {trend_label}"
        )

        return SignalContract(
            symbol=symbol,
            timeframe=timeframe,
            signal=direction,
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
