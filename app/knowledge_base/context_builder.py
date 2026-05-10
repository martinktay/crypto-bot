from app.models.entities import KnowledgeDocument
from app.schemas.signal import SignalContract


def build_signal_context(signal: SignalContract, docs: list[KnowledgeDocument]) -> str:
    snippets = [f"- {d.title}: {d.content[:140]}" for d in docs]
    header = f"Signal {signal.symbol} {signal.timeframe} {signal.signal} quality={signal.quality_score:.1f}"
    return "\n".join([header, *snippets])
