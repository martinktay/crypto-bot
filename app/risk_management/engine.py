from datetime import timedelta
from typing import Any

from app.core.config import settings
from app.core.enums import SignalDirection
from app.core.state import RuntimeState
from app.schemas.signal import SignalContract


class RiskEngine:
    def validate_signal(self, signal: SignalContract) -> tuple[bool, str]:
        """Check signal-level risk: direction and risk-reward ratio."""
        if signal.signal == SignalDirection.HOLD:
            return False, "HOLD signal not executable"

        per_unit_risk = abs(signal.entry_price - signal.stop_loss)
        per_unit_reward = abs(signal.take_profit - signal.entry_price)
        rr = per_unit_reward / max(per_unit_risk, 1e-9)

        if rr < settings.min_risk_reward_ratio:
            return False, f"Risk-reward too low: {rr:.2f} (min {settings.min_risk_reward_ratio})"

        # Volatility check (ATR)
        if signal.atr_value and signal.atr_value > 0:
            sl_distance = abs(signal.entry_price - signal.stop_loss)
            # Minimum stop should be at least 1.5x ATR
            min_sl_dist = signal.atr_value * 1.5
            if sl_distance < min_sl_dist:
                return False, f"Stop loss too tight for volatility: {sl_distance:.2f} < {min_sl_dist:.2f} (1.5x ATR)"

        return True, "approved"

    def validate_runtime_limits(
        self, state: RuntimeState, signal: SignalContract
    ) -> tuple[bool, str]:
        """Check runtime limits: signal cooldown."""
        for prev in state.signals[:10]:
            if prev.symbol == signal.symbol and prev.signal == signal.signal:
                if signal.timestamp - prev.timestamp < timedelta(
                    minutes=settings.signal_cooldown_minutes
                ):
                    return False, "Signal cooldown active"

        return True, "runtime limits passed"


