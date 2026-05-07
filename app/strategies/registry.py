from app.strategies.base import Strategy
from app.strategies.breakout_volume import BreakoutVolumeStrategy
from app.strategies.ema_rsi import EmaRsiStrategy
from app.strategies.hybrid_ai import HybridAIStrategy


STRATEGIES: dict[str, type[Strategy]] = {
    EmaRsiStrategy.name: EmaRsiStrategy,
    BreakoutVolumeStrategy.name: BreakoutVolumeStrategy,
    HybridAIStrategy.name: HybridAIStrategy,
}


def build_strategy(name: str) -> Strategy:
    strategy_cls = STRATEGIES.get(name, EmaRsiStrategy)
    return strategy_cls()
