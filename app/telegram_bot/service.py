from app.core.enums import TradingMode
from app.schemas.signal import SignalContract


class TelegramNotifier:
    def build_signal_message(self, signal: SignalContract, ai_explanation: str, mode: TradingMode) -> str:
        return (
            "🚨 SIGNAL ALERT\n"
            f"Pair: {signal.symbol}\n"
            f"Timeframe: {signal.timeframe}\n"
            f"Signal: {signal.signal}\n"
            f"Entry: {signal.entry_price:.2f}\n"
            f"Stop Loss: {signal.stop_loss:.2f}\n"
            f"Take Profit: {signal.take_profit:.2f}\n"
            f"Confidence: {signal.confidence:.1f}%\n"
            f"Reason: {signal.reason}\n"
            f"AI Insight: {ai_explanation}\n"
            f"Mode: {mode.value}\n"
            f"Time: {signal.timestamp.isoformat()}"
        )
