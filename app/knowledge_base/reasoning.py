from app.schemas.signal import SignalContract


class ReasoningEngine:
    def explain(self, signal: SignalContract, context: str) -> str:
        return (
            "AI advisory: setup aligns with stored strategy context; "
            f"signal={signal.signal}, confidence={signal.confidence:.1f}. "
            "Risk constraints remain authoritative."
        )
