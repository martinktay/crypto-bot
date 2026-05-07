import sys
import os
import json
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import SessionLocal
from app.db.repository import StateRepository
from app.knowledge_base.reasoning import ReasoningEngine
from app.knowledge_base.embeddings import EmbeddingProvider
from app.models.entities import Signal, BacktestHistory
from app.core.enums import SignalDirection
from sqlalchemy import select

def migrate():
    db = SessionLocal()
    repo = StateRepository(db)
    reasoner = ReasoningEngine()
    embedder = EmbeddingProvider()

    print("--- Starting Migration of Historical Lessons ---")

    # 1. Migrate Backtest History
    try:
        backtests = db.execute(select(BacktestHistory)).scalars().all()
        print(f"Found {len(backtests)} backtest records.")
        for bt in backtests:
            # Create a mock result object for the reasoner
            class MockResult:
                def __init__(self, bt):
                    self.strategy = bt.strategy
                    self.symbol = bt.symbol
                    self.best_sharpe = bt.sharpe_ratio
                    self.best_return_pct = ((bt.final_balance - bt.initial_balance) / max(bt.initial_balance, 1e-9)) * 100
                    self.best_params = bt.params
                    self.total_simulations = bt.total_trades # Approximation
            
            lesson_text = reasoner.analyze_simulation_result(MockResult(bt))
            vector = embedder.embed(lesson_text)
            repo.ingest_knowledge_document(
                title=f"Evolution Lesson: {bt.strategy} on {bt.symbol}",
                content=lesson_text,
                source_type="evolution_archive",
                vector=vector,
                metadata={"backtest_id": bt.id, "sharpe": bt.sharpe_ratio}
            )
            print(f"  [+] Migrated Backtest {bt.id}: {lesson_text[:60]}...")
    except Exception as e:
        print(f"  [!] Error migrating backtests: {e}")

    # 2. Migrate High-Confidence Signals
    try:
        signals = db.execute(select(Signal).where(Signal.confidence >= 80)).scalars().all()
        print(f"Found {len(signals)} high-confidence signals.")
        for sig in signals:
            # Use raw value for prompt
            signal_type = sig.signal.value if hasattr(sig.signal, "value") else str(sig.signal)
            lesson_text = f"Historical High Confidence Signal: {signal_type} on {sig.symbol} with {sig.confidence}% confidence. Reason: {sig.reason}"
            vector = embedder.embed(lesson_text)
            repo.ingest_knowledge_document(
                title=f"Archived Signal: {sig.symbol} {signal_type}",
                content=lesson_text,
                source_type="signal_archive",
                vector=vector,
                metadata={"signal_id": sig.id, "confidence": sig.confidence}
            )
            print(f"  [+] Migrated Signal {sig.id}: {lesson_text[:60]}...")
    except Exception as e:
        print(f"  [!] Error migrating signals: {e}")

    print("--- Migration Complete ---")
    db.close()

if __name__ == "__main__":
    migrate()
