from app.schemas.signal import SignalContract


class ReasoningEngine:
    def explain(self, signal: SignalContract, context: str) -> str:
        return (
            f"Setup {signal.signal} on {signal.symbol} {signal.timeframe}. "
            f"Context: {context[:180]} "
            "AI note is advisory only; hard risk rules remain enforced."
        )
