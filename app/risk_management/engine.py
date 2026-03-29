from app.core.config import settings
from app.core.enums import SignalDirection
from app.schemas.signal import SignalContract


class RiskEngine:
    def validate_signal(self, signal: SignalContract) -> tuple[bool, str]:
        if signal.signal == SignalDirection.HOLD:
            return False, "HOLD signal not executable"
        rr = abs(signal.take_profit - signal.entry_price) / max(abs(signal.entry_price - signal.stop_loss), 1e-9)
        if rr < 1.2:
            return False, f"Risk-reward too low: {rr:.2f}"
        return True, "approved"

    def position_size(self, account_balance: float, signal: SignalContract) -> float:
        risk_amount = account_balance * settings.risk_per_trade
        per_unit_risk = abs(signal.entry_price - signal.stop_loss)
        return 0.0 if per_unit_risk <= 0 else risk_amount / per_unit_risk
