import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from app.core.config import settings
from app.core.enums import SignalDirection
from app.optimization.rl_service import RLService
from app.schemas.signal import SignalContract
from app.strategies.base import Strategy
from app.utils.candlestick_patterns import gate_for_direction
from app.utils.candles import candle_close_timestamp
from app.utils.indicators import resolve_htf_gate

logger = logging.getLogger(__name__)


class HybridAIStrategy(Strategy):
    """Hybrid: indicator features + RL policy; levels align with other strategies.

    Stop / take-profit use ATR-derived distances (like ``ema_rsi``) so the
    risk engine and outcome tracker see consistent geometry. The RL policy
    only picks direction — it does **not** rewrite numeric risk levels.
    Higher-timeframe trend (EMA200) filters trades when
    ``params['higher_tf_candles']`` or ``params['multi_htf_candles']`` is provided by the pipeline.
    """

    name = "hybrid_ai"

    def __init__(self, model_name: str = "ppo_trading_bot") -> None:
        self.rl_service = RLService()
        self.model_name = model_name
        self.model = self.rl_service.load_model(model_name)

        self.window_size = 10
        self.feature_cols = ["rsi", "ema_fast", "ema_slow", "atr_value", "volume"]

    def generate(
        self,
        symbol: str,
        timeframe: str,
        candles: pd.DataFrame,
        params: dict[str, Any] | None = None,
    ) -> SignalContract:
        from app.utils.indicators import add_indicators

        p = params or {}
        df = add_indicators(candles)

        last_row = df.iloc[-1] if len(df) else None

        if self.model is None:
            m_name = p.get("model_name", self.model_name)
            self.model = self.rl_service.load_model(m_name)
            if self.model is None:
                logger.warning(
                    "HybridAI model '%s' not found. Defaulting to HOLD.", m_name
                )
                return self._hold_signal(
                    symbol,
                    timeframe,
                    candles,
                    df,
                    f"HybridAI model '{m_name}' not found",
                )

        if len(df) < self.window_size:
            logger.warning(
                "Not enough bars for RL window (%d < %d). Defaulting to HOLD.",
                len(df),
                self.window_size,
            )
            return self._hold_signal(
                symbol,
                timeframe,
                candles,
                df,
                f"Insufficient history for RL window ({len(df)} bars)",
            )

        obs_df = df.iloc[-self.window_size :][self.feature_cols]
        observation = obs_df.values.astype(np.float32)
        action = self.rl_service.predict_action(self.model, observation)

        direction = SignalDirection.HOLD
        if action == 1:
            direction = SignalDirection.LONG
        elif action == 2:
            direction = SignalDirection.SHORT

        price = float(last_row["close"])
        atr_raw = last_row.get("atr_value")
        atr_value = float(atr_raw) if pd.notna(atr_raw) else 0.0
        atr_sl_mult = float(p.get("atr_sl_multiple", 2.0))
        tp_mult = float(p.get("take_profit_r_multiple", settings.take_profit_r_multiple))
        sl_distance = atr_value * atr_sl_mult if atr_value > 0 else price * 0.01

        block_long, block_short, trend_bits = resolve_htf_gate(p)

        if direction == SignalDirection.LONG:
            if block_long:
                return self._hold_signal(
                    symbol,
                    timeframe,
                    candles,
                    df,
                    f"RL LONG blocked by higher-TF downtrend; {trend_bits}",
                )
            blocked, detail, candle_extra = gate_for_direction(df, "LONG")
            if blocked:
                return self._hold_signal(
                    symbol,
                    timeframe,
                    candles,
                    df,
                    f"RL LONG blocked by candlestick ({detail}); {trend_bits}",
                )
            stop = price - sl_distance
            take = price + sl_distance * tp_mult
            mh = last_row.get("macd_hist", 0)
            if pd.isna(mh):
                mh = 0.0
            conf = float(
                min(
                    92.0,
                    max(
                        52.0,
                        60.0 + abs(float(mh)) / max(price, 1e-9) * 5000,
                    ),
                )
            )
        elif direction == SignalDirection.SHORT:
            if block_short:
                return self._hold_signal(
                    symbol,
                    timeframe,
                    candles,
                    df,
                    f"RL SHORT blocked by higher-TF uptrend; {trend_bits}",
                )
            blocked, detail, candle_extra = gate_for_direction(df, "SHORT")
            if blocked:
                return self._hold_signal(
                    symbol,
                    timeframe,
                    candles,
                    df,
                    f"RL SHORT blocked by candlestick ({detail}); {trend_bits}",
                )
            stop = price + sl_distance
            take = price - sl_distance * tp_mult
            mh = last_row.get("macd_hist", 0)
            if pd.isna(mh):
                mh = 0.0
            conf = float(
                min(
                    92.0,
                    max(
                        52.0,
                        60.0 + abs(float(mh)) / max(price, 1e-9) * 5000,
                    ),
                )
            )
        else:
            return self._hold_signal(
                symbol, timeframe, candles, df, f"RL HOLD (action={action})"
            )

        reason = (
            f"RL direction action={direction.value} (policy={action}); "
            f"ATR SL×{atr_sl_mult:.1f}, R={tp_mult:.1f}x; {trend_bits}"
        )
        if candle_extra:
            reason = f"{reason}; {candle_extra}"

        return SignalContract(
            symbol=symbol,
            timeframe=timeframe,
            signal=direction,
            entry_price=price,
            stop_loss=float(stop),
            take_profit=float(take),
            quality_score=conf,
            confidence=conf,
            order_type="LIMIT",
            reason=reason,
            atr_value=atr_value,
            timestamp=candle_close_timestamp(last_row),
        )

    def _hold_signal(
        self,
        symbol: str,
        timeframe: str,
        candles: pd.DataFrame,
        ind_df: pd.DataFrame | None,
        reason: str,
    ) -> SignalContract:
        df = ind_df if ind_df is not None and len(ind_df) else candles
        last = df.iloc[-1] if df is not None and len(df) else None
        price = float(last["close"]) if last is not None else 0.0
        atr_v = None
        if last is not None and "atr_value" in last.index and pd.notna(last["atr_value"]):
            atr_v = float(last["atr_value"])
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
            atr_value=atr_v,
            timestamp=candle_close_timestamp(last) if last is not None else datetime.now(timezone.utc),
        )
